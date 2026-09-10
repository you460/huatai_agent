import psycopg2
import json
import time
import http.client
import ssl
import re
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlparse
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    LLM_TEMPERATURE, LLM_MAX_RETRIES,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_CONFIG,
    AGENT_MAX_ROUNDS, SQL_MAX_EXEC_ERRORS, SQL_STATEMENT_TIMEOUT_MS,
    SQL_MAX_RESULT_ROWS
)
from metadata_tools import search_table, get_table_schema, get_metric, match_business_rules, METADATA
from security_guard import check_sql_safety

# 用标准库 http.client 直连大模型（绕开 httpx/urllib3 在 Windows 上对 SSL 套接字的兼容问题）
_API = urlparse(DEEPSEEK_BASE_URL)
_API_HOST = _API.netloc or "api.deepseek.com"
_API_PATH = _API.path.rstrip("/") + "/chat/completions"
_SSL_CTX = ssl.create_default_context()

@dataclass
class AgentResult:
    """Agent 已验证过的一次查询结果，供界面和评测复用。"""
    sql: str
    columns: list
    rows: list


@dataclass
class AgentFailure:
    """return_result 模式下保留失败阶段，供评测记录可审计证据。"""
    kind: str
    message: str
    details: dict | None = None

    def __bool__(self):
        return False


@dataclass
class LLMCallFailure:
    """模型调用失败的脱敏诊断，避免把网络问题误报为无内容响应。"""
    message: str
    details: dict


def _safe_error_summary(error):
    """保留可诊断的错误摘要，同时绝不把鉴权值写入日志或评测产物。"""
    summary = str(error)
    if DEEPSEEK_API_KEY:
        summary = summary.replace(DEEPSEEK_API_KEY, '***')
    summary = re.sub(r'Bearer\s+\S+', 'Bearer ***', summary, flags=re.IGNORECASE)
    return summary[:240]

# 工具定义
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_table",
            "description": "根据关键词搜索相关表，返回表名、中文名、用途及完整字段摘要（含字段名、中文名、枚举取值、关联键）。字段摘要已足够生成SQL，优先用此工具，通常无需再调用get_table_schema。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，比如'客户'、'资产'、'交易'、'持仓'、'产品'等"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": "获取单张表的完整字段信息（含长描述）。仅当search_table返回的字段摘要不足以生成SQL时才调用，通常不需要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "表名，比如'ads_cust_info_d'、'dws_cust_aset_d'"
                    }
                },
                "required": ["table_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_metric",
            "description": "根据关键词搜索业务指标的定义和计算公式，比如'总资产'、'交易金额'、'资金流入'。当用户问题涉及到需要计算的业务指标，不确定指标怎么计算时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，比如'总资产'、'交易金额'、'资金流入'"
                    }
                },
                "required": ["keyword"]
            }
        }
    }
]

# 给大模型的系统提示
SYSTEM_PROMPT = f"""你是一个专业的SQL生成助手，专门帮助用户从数据库中查询数据。

工作流程（核心原则：用最少的工具调用生成正确SQL）：
1. 理解问题，确定核心要查什么：哪张表、哪些字段、什么筛选条件、什么聚合方式
2. 调用 search_table 搜索最核心的1个关键词（如"客户""资产""持仓""交易""产品"），它一次返回相关表及其完整字段摘要
3. 字段摘要里已包含字段名、中文名、枚举取值、关联键，据此直接生成 SQL，通常不需要再调用 get_table_schema
4. 若问题涉及业务指标（总资产、交易金额、资金流入等），调用 get_metric 拿标准计算公式

复杂查询技巧：
- 多表关联：先确定主表，再一步步关联其他表，不要一次性写太多JOIN
- 子查询/CTE：复杂计算先做成子查询或WITH...AS，再外层汇总，逻辑更清晰
- 占比/差值：先分别算分子分母或两个分类的值，再计算最终结果
- 分组统计：先确定分组维度，再确定聚合指标，最后排序

工具调用规则（严格遵守，硬性要求）：
- search_table 只搜 1 个最核心关键词，不要搜多个词、不要重复搜
- search_table 已返回字段摘要，除非某个字段含义确实不清，否则不要再调 get_table_schema
- 简单问题（计数、单表筛选）：search_table 搜 1 次后直接生成 SQL
- 复杂问题（多表关联）：search_table 搜 1-2 次（不同关键词）拿全相关表字段，再生成 SQL

全局规则：
{json.dumps(METADATA['global_rules'], ensure_ascii=False, indent=2)}

补充约定：
- 【最终回复硬性格式】完成工具调用后，回复必须只含一条可执行SQL，并且首词只能是 SELECT 或 WITH；禁止任何中文分析、确认过程、Markdown代码块、注释、第二段SQL或重复SQL
- 枚举/字典字段：字段摘要里已内嵌枚举取值（如 gender_cd 字典类型500: 取值[5000002=男,...]）。筛选/过滤直接用内嵌代码值（where gender_cd='5000002'），无需 join 字典表；只有展示中文时才 join dim_public，且 code_type_id 必须用摘要里标注的字典类型（如 '500'）。若摘要标注"...共N个"（取值没内嵌全），用模糊匹配（where b.describe like '%医生%'）
- 以下三张维表查询时不要加data_dt条件：dim_branch、dim_product、dim_public；只有dwd_/dws_/ads_开头的事实表才需要加data_dt
- 学历枚举值是"学士""硕士""博士"，不是"本科"；"本科及以上"用 describe IN ('学士','硕士','博士')
- 只返回题目明确要求的列，不要返回额外/中间列：问"占比/比率"只返回 维度列+占比列（不要返回分子、分母、count等中间列）；问"平均年龄"只返回平均年龄；问"分布/排名"只返回 维度列+聚合指标列。【唯一例外】问"盈亏情况"时必须返回完整6列：pty_id、期初总资产(20260101)、期末总资产(20260331)、资金流入、资金流出、盈亏（盈亏=期末-期初+流出-流入）
- 【必须遵守，客户列表与数量】问“哪些客户/查询客户/前N的客户”等列表或排名问题时，返回 pty_id（客户号，不用 name）及题目要求的属性/排名依据；“交易金额前N的客户/总资产前N的客户”等排名题，排名依据本身也是必须返回的列，再返回题目要求的属性，列顺序为 pty_id、排名指标、题目要求的属性。问“客户等级/性别/学历/职业/账户状态”等名称时必须关联 dim_public 返回 describe，不能返回 *_cd 编码；**分组统计场景同样适用**：如"统计不同性别的客户数量"必须 JOIN dim_public 后 GROUP BY describe（中文），禁止 GROUP BY gender_cd 输出编码；只有题目明确问“多少/数量/人数/几位”时才返回 COUNT，不要把“哪些客户”改成计数
- 产品分类：一级分类用 up_prdt_type_name（债券/股票/开放式基金/理财产品/衍生品等），二级分类用 prdt_type_name（A股/科创板/创业板/ETF/沪港通/深港通/新三板/北交所/LOF等）。"债券"是一级分类，"A股/科创板/ETF/沪港通/深港通"是二级分类；不要用 prdt_name LIKE '%债%' 表示债券，会误纳"交易型债券ETF"等开放式基金
- 【必须遵守，机构输出】问“各分公司/每个分公司”时，SELECT 和 GROUP BY 只能包含 b.up_org_name，不能额外返回 b.org_name；问“各营业部/每个营业部”时，SELECT 和 GROUP BY 都必须同时包含 b.up_org_name、b.org_name；只返回 org_name 不算完整答案。**无论统计的是客户数、交易/买入金额还是平均值，该规则都适用，模板：SELECT b.up_org_name, b.org_name, 聚合(...) ... GROUP BY b.up_org_name, b.org_name**
- 【必须遵守，机构与地域】题目出现“XX分公司”是机构条件，必须关联 dim_branch，并用 up_org_name='XX分公司' 筛选；题目出现“XX营业部”必须用 org_name='XX营业部' 筛选。两者都不能用客户表的 prov_name 或 city_name 代替；涉及分公司/营业部时，除客户表外还要搜索“营业部”表。
- 月份与季度区分：问"X月"指该自然月（"3月"= data_dt between '20260301' and '20260331'），问"Q1"才是季度（between '20260101' and '20260331'），两者不要混用
- 年龄段默认：<30、[30,50)、[50,60)、[60,)；标签严格用这四种符号，不要用中文标签（如"小于30""大于60"）
- 【年龄条件必须逐字判断】"X岁以上/X岁及以上/年龄在X岁以上"都包含X岁，必须写 cust_age>=X；只有"大于X岁/超过X岁"才写 cust_age>X。"X岁以下/及以下"包含X岁，写 cust_age<=X
- "普通客户"指客户等级"紫金理财卡客户"(cust_lvl_cd='1000005')，即基础理财卡，不是"非钻石卡客户"；不要用 describe like '%普通%' 或 NOT LIKE '%钻石卡%' 表示（字典里没有"普通"字样）
- 计算"平均持仓市值/平均持仓金额"：先在子查询按持仓表 pty_id 汇总，再 LEFT JOIN 客户并以客户表 pty_id 保持一名客户一行，最后 AVG(coalesce(h.total_mkt_val,0))；禁止关联后按持仓表 h.pty_id 分组，否则所有无持仓客户的 NULL 会被合并成一行
- 计算"平均总资产"：问各省份、各营业部、每个分公司等分组比较时，以客户快照为完整母体，LEFT JOIN 指定日期资产，无资产记录按0纳入 AVG；只问某个有专名的单一省份、分公司或营业部时，必须从指定日期资产记录出发使用 INNER JOIN，不得把无资产记录按0纳入。题目明确说明全部客户、仅有资产客户或无记录按0时，以题目说明为准。问两个群体的平均总资产差值时，直接用两个未 ROUND 的 AVG 相减，题目未要求时不要提前或额外 ROUND
- 【必须遵守，快照日期】关联不同表绝不能写 a.data_dt=b.data_dt；客户快照常为20260531，而资产、持仓等业务快照常为20260331。各表日期必须分别写在 WHERE 或对应 JOIN 条件中
- 佣金率/占比/比率类指标返回小数（0.001 表示 0.1%），不要乘100；“整体交易佣金率”= SUM(buy_rake+sell_rake) / NULLIF(SUM(buy_amt+sell_amt),0)，不是客户佣金率的简单平均
- 产品维度分组：统计"每个产品/各产品"的总市值/总金额/总笔数时，按产品名 prdt_name 分组（同名产品要合并），只返回产品名+汇总值；不要把 prdt_id 加进 GROUP BY 或 SELECT。"产品前N名/交易金额前N的产品/成交笔数前N的产品"也必须先按 prdt_name 汇总，再按该汇总值排序并 LIMIT N；禁止先按 prdt_id 取前N后再展示产品名。**CTE/子查询里也必须先 JOIN dim_product 再 GROUP BY prdt_name，禁止在 CTE 里按 prdt_id 聚合、外层才 JOIN 产品表（同名产品会被拆成两条导致数值偏小）**
- 占比/比率/渗透率：两个整数相除在SQL里结果恒为0，必须写成 分子*1.0/分母 或 CAST(分子 AS numeric)/分母（例：count(distinct case when ... end)*1.0/count(*)）；按各维度输出占比时只返回维度+占比，题目未指定顺序也默认 ORDER BY 占比 DESC；不存在目标客户的分组分子为0，使用条件聚合或 COALESCE(左连接分子,0)，不能返回 NULL
- 资产/金额/市值“分布”默认返回分组维度+对应汇总值；只有题目明确要求客户数、人数或数量时才增加 COUNT，禁止自行添加数量列
- 所有计算表达式必须写体现业务语义的显式 AS 别名，尤其是差值、占比、平均值、总额和数量；禁止返回 ?column?、sum、round 等数据库默认列名
- 【必须遵守，年龄边界】凡是"X岁以上/X岁及以上"（X为任意年龄，如40、50、60）都包含X岁，一律写 cust_age >= X，禁止写 cust_age > X；只有题目明确说"超过X岁/大于X岁"时才用 > X。同理，"X岁以下/及以下"含X岁，用 <= X；"不足X岁"用 < X
- 资金转入/流入 = cash_in+tran_in+assign_in 三类合计；资金转出/流出 = cash_out+tran_out+assign_out 三类合计，不要只算其中一类
- "高净值客户"指总资产(普通账户nm_tot_aset+信用账户fc_pur_aset)超过某阈值的客户，不是客户等级（钻石卡/白金卡等）
- "盈亏"= 期末总资产 - 期初总资产 + 期间资金流出 - 期间资金流入（净资产变动口径），不是买卖价差；2026年Q1的期初资产快照固定取 data_dt='20260101'，期末取 data_dt='20260331'，不要取上一年末
- "日均资产"= 期间内每日总资产之和 / 期间天数（2026年Q1为90天），不要除以该客户实际出现天数；日均资产排名或展示时写 ROUND(日均资产,2)
- "某客户买入/交易金额>X"指该客户在期间内累计金额>X：先按 pty_id 分组 sum 再用 HAVING 过滤，不要按单行(单笔)过滤。若题目问"满足该条件的客户有多少/数量"，必须用两层结构：SELECT COUNT(*) FROM (SELECT pty_id ... GROUP BY pty_id HAVING SUM(...)>X) t；禁止外层写 COUNT 同时又 GROUP BY pty_id（会返回多行而不是一个总数）
- 【交易量口径】"交易量/交易额"指金额 buy_amt+sell_amt，不是份额 buy_mnt/sell_mnt；"满足条件客户的营业部分布/分布情况"是按 up_org_name,org_name 汇总这些客户的该金额（SUM），不是 COUNT 客户个数
- 【客户地域分布】"满足条件客户的省份/城市/地域分布"默认按地域统计 COUNT(DISTINCT pty_id)，返回地域+客户数；只有明确问交易金额、资产或市值的地域分布时才 SUM 对应金额
- 【客户排名字段顺序】客户前N/Top N/排名题要求附加属性时，最终 SELECT 顺序必须是 pty_id、排名指标、题目要求的属性；排名指标紧跟 pty_id，不能放到最后
- 【ROUND口径】平均年龄、平均持仓市值等"平均值"统一 ROUND(结果,2)；总资产、交易金额及其排名、求和值不 ROUND，保留数据库原始精度
- 产品名筛选用精确匹配 prdt_name='X'，不要用 LIKE '%X%'；【必须遵守，同名股票】招商银行、中国平安等同名股票必须同时写 prdt_name='X' 和 prdt_type_name='A股' 消歧；“普通账户/信用账户”只限制题目直接修饰的表，例如“普通账户持有中国平安”只在持仓表写 h.sys_source='nm'，不能顺带限制招商银行交易表
- 产品分类输出严格按题目层级：明确问一级分类只返回 up_prdt_type_name，明确问二级分类只返回 prdt_type_name；只有题目要求同时展示两级或问特定客户持有产品属于哪些大类/分类时才返回两级
- 产品分类客户渗透率默认只统计指定快照实际出现持仓的分类，应从持仓事实表出发 INNER JOIN 产品表；题目没有明确要求全部分类时，不得从产品表 LEFT JOIN 持仓补出零渗透率分类
- 【必须遵守，持仓市值阈值】题目说“持有X市值超过Y”时，先按客户 pty_id 汇总该产品的 SUM(COALESCE(mkt_val,0))，再用 HAVING SUM(...) > Y 筛选；不能只用单条持仓记录 mkt_val > Y。
- 数值字段相加/求和前用 coalesce(字段,0) 处理 NULL，避免 NULL 使整行结果为 NULL
- 【必须遵守，二次聚合】按"XX交易量/金额>阈值"筛选客户后问"营业部/分公司分布/排名"时，先在子查询按 pty_id 聚合并用 HAVING 筛客户，再在外层按 up_org_name、org_name 汇总 sum(交易金额)；最终 GROUP BY 不能包含 pty_id，也不要用 count(客户数)。
- 问"其持有的产品属于哪些大类/分类"时，最终必须返回一级分类 up_prdt_type_name、二级分类 prdt_type_name、sum(mkt_val) 三列，并同时按两个分类字段分组；不能只按一级分类汇总，不要只返回去重分类名或 count(客户数)

示例：
问：客户信息表中总共有多少位客户
答：SELECT COUNT(*) FROM ads_cust_info_d WHERE data_dt='20260531'

问：男性客户有多少个
答：SELECT COUNT(*) FROM ads_cust_info_d WHERE data_dt='20260531' AND gender_cd='5000002'
"""

# 工具名到函数的映射
TOOL_FUNCTIONS = {
    "search_table": search_table,
    "get_table_schema": get_table_schema,
    "get_metric": get_metric
}


def extract_sql(text):
    """从大模型输出中提取SQL语句，优先取最后一个```sql代码块，去掉前后解释文字"""
    import re
    # 优先取最后一个 ```sql ... ``` 代码块的内容（模型偶尔会输出多段解释+多个代码块）
    blocks = re.findall(r'```sql\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
    if blocks:
        text = blocks[-1]
    else:
        text = text.replace("```sql", "").replace("```", "")
    text = text.strip()
    # 找第一个 SELECT 或 WITH
    match = re.search(r'(SELECT|WITH)\s', text, re.IGNORECASE)
    if match:
        sql = text[match.start():].strip()
        # 去掉末尾的分号
        if sql.endswith(';'):
            sql = sql[:-1].strip()
        return sql
    if re.match(r'(DELETE|UPDATE|INSERT|DROP|ALTER|TRUNCATE|CREATE)\b', text, re.IGNORECASE):
        return text
    return ''


def check_question_sql_consistency(question, sql):
    """检查少量可确定的自然语言边界，发现偏差时交回模型修正。"""
    inclusive_ages = re.findall(r'(\d+)岁(?:及)?以上', question)
    for age in inclusive_ages:
        wrong_boundary = re.search(
            rf'\bcust_age\s*>\s*{re.escape(age)}\b', sql, re.IGNORECASE
        )
        if wrong_boundary:
            return False, f'题目“{age}岁以上”包含{age}岁，cust_age 必须使用 >= {age}'
    normalised_sql = re.sub(r'\s+', ' ', sql).casefold()
    if re.search(r'产品.*渗透率|渗透率.*产品', question):
        if re.search(r'from\s+dim_product\b.*left\s+join\s+dwd_cust_hold_d\b', normalised_sql):
            return False, '产品渗透率默认以实际持仓分类为范围，必须从持仓表出发 INNER JOIN 产品表，不能补出零持仓分类'
    if re.search(r'平均持仓(?:市值|金额)|持仓(?:市值|金额).*平均', question):
        if ('left join dwd_cust_hold_d' in normalised_sql and
                re.search(r'group\s+by[^;]*\b(?:h|hold)\.pty_id\b', normalised_sql)):
            return False, '无持仓客户必须保持客户粒度；LEFT JOIN 后不能按持仓表 pty_id 分组，请先按持仓汇总再关联客户'
    if '盈亏' in question:
        begin_position = max(
            normalised_sql.rfind(marker)
            for marker in (' as begin_aset', ' as bgn_aset', ' as aset_begin', ' as 期初总资产', ' as 期初资产')
        )
        end_position = max(
            normalised_sql.rfind(marker)
            for marker in (' as end_aset', ' as end_asset', ' as aset_end', ' as 期末总资产', ' as 期末资产')
        )
        if begin_position >= 0 and end_position >= 0 and begin_position > end_position:
            return False, '盈亏明细固定先返回期初资产、再返回期末资产；请调整最终SELECT字段顺序'
    if ('营业部' in question and re.search(r'平均|均值|人均', question) and
            re.search(r'group\s+by\s+\w+\.org_id\b', normalised_sql) and
            not re.search(r'group\s+by\s+[^)]*up_org_name[^)]*org_name', normalised_sql)):
        return False, '营业部平均值必须直接按最终展示的up_org_name、org_name分组，不能先按org_id聚合后再关联名称'
    return True, None


def _msg_to_dict(m):
    """把消息（dict 或 OpenAI 风格对象）统一转成可序列化的 dict。"""
    if isinstance(m, dict):
        return m
    d = {"role": getattr(m, "role", "assistant"), "content": getattr(m, "content", None)}
    tcs = getattr(m, "tool_calls", None)
    if tcs:
        d["tool_calls"] = [
            {"id": tc.id, "type": getattr(tc, "type", "function"),
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tcs
        ]
    return d


def call_llm(messages, allow_tools=True):
    """调用大模型，失败自动重试并返回脱敏失败证据。"""
    last_error = None
    for retry in range(LLM_MAX_RETRIES):
        try:
            request_body = {
                "model": DEEPSEEK_MODEL,
                "messages": [_msg_to_dict(m) for m in messages],
                "temperature": LLM_TEMPERATURE,
            }
            if allow_tools:
                request_body.update({"tools": TOOLS, "tool_choice": "auto"})
            body = json.dumps(request_body, ensure_ascii=False).encode("utf-8")

            conn = http.client.HTTPSConnection(_API_HOST, 443, context=_SSL_CTX, timeout=180)
            conn.request("POST", _API_PATH, body=body, headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + DEEPSEEK_API_KEY,
            })
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            conn.close()

            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}: {data[:200]}")

            j = json.loads(data)
            msg = j["choices"][0]["message"]
            tool_calls = msg.get("tool_calls")
            message = SimpleNamespace(
                role=msg.get("role", "assistant"),
                content=msg.get("content"),
                tool_calls=(
                    [SimpleNamespace(
                        id=tc["id"],
                        type=tc.get("type", "function"),
                        function=SimpleNamespace(name=tc["function"]["name"],
                                                 arguments=tc["function"]["arguments"])
                    ) for tc in tool_calls]
                    if tool_calls else None
                ),
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        except Exception as e:
            last_error = _safe_error_summary(e)
            if retry < LLM_MAX_RETRIES - 1:
                print(f"大模型调用失败（第{retry+1}次）: {last_error[:100]}，重试中...")
                time.sleep(1)
            else:
                print(f"大模型调用失败，已重试{LLM_MAX_RETRIES}次: {last_error[:100]}")
    return LLMCallFailure(
        message=f"模型调用失败，已重试{LLM_MAX_RETRIES}次: {last_error or '未知错误'}",
        details={'stage': 'model_api', 'attempts': LLM_MAX_RETRIES, 'error': last_error},
    )


def execute_tool_call(tool_call, tool_cache):
    """执行一次工具调用，带缓存。"""
    tool_name = tool_call.function.name
    
    # 解析工具参数
    try:
        tool_args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError as e:
        print(f"工具参数解析失败: {e}")
        return {"error": f"参数格式错误: {e}"}, None
    
    print(f"大模型调用工具: {tool_name}({tool_args})")
    
    # 生成缓存key
    cache_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True, ensure_ascii=False)}"
    
    # 检查缓存
    if cache_key in tool_cache:
        print("（缓存命中，直接返回）")
        return tool_cache[cache_key], cache_key
    
    # 执行工具函数
    try:
        tool_function = TOOL_FUNCTIONS[tool_name]
        tool_result = tool_function(**tool_args)
    except Exception as e:
        print(f"工具执行失败: {e}")
        tool_result = {"error": str(e)}
    
    tool_cache[cache_key] = tool_result
    return tool_result, cache_key


def run_agent(question, return_result=False):
    """运行 Agent；return_result=True 时复用已验证的 SQL 结果。"""
    relevant_rules = match_business_rules(question)
    rule_context = ''
    if relevant_rules:
        rule_context = '\n\n本题适用的业务规则：\n' + '\n'.join(
            f'- {rule}' for rule in relevant_rules.values()
        )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question + rule_context}
    ]
    
    exec_error_count = 0
    tool_cache = {}
    tool_call_counts = {}
    force_next_sql = False
    last_validation_error = None
    last_response_error = None
    last_sql = None

    def fail(kind, message, details=None):
        return AgentFailure(kind, message, details) if return_result else None
    
    for round_num in range(AGENT_MAX_ROUNDS):
        print(f"\n--- 第 {round_num+1} 轮大模型调用 ---")
        
        force_sql = force_next_sql or round_num >= AGENT_MAX_ROUNDS - 2
        if force_sql:
            correction = (
                f" 上一次SQL错误：{last_validation_error}。必须针对该错误修正。"
                if last_validation_error else ''
            )
            final_instruction = {
                "role": "user",
                "content": (
                    "已有工具信息足够回答。现在禁止继续调用工具，必须只输出一条以 SELECT 或 WITH 开头的可执行SQL，不要解释。"
                    + correction
                )
            }
            call_messages = [messages[0], messages[1], final_instruction]
        else:
            call_messages = messages
        response = call_llm(call_messages, allow_tools=not force_sql)
        if isinstance(response, LLMCallFailure):
            return fail('agent_generation_error', response.message, response.details)
        if not response:
            return fail('agent_generation_error', '模型调用未返回响应', {'stage': 'model_api'})
        
        message = response.choices[0].message
        messages.append(message)
        
        # 处理工具调用
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_result, cache_key = execute_tool_call(tool_call, tool_cache)
                tool_call_counts[cache_key] = tool_call_counts.get(cache_key, 0) + 1
                if tool_call_counts[cache_key] >= 2:
                    force_next_sql = True
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })
                print(f"工具返回结果: {json.dumps(tool_result, ensure_ascii=False)[:200]}...")
            messages.append({
                "role": "user",
                "content": "工具结果已提供。若还缺信息可继续调用工具；若可以回答，必须只输出一条以 SELECT 或 WITH 开头的可执行SQL，不要解释。"
            })
            continue
        
        # 模型返回最终 SQL
        raw_content = (message.content or '').strip()
        if not raw_content:
            return fail(
                'agent_generation_error', '模型响应不含文本或工具调用',
                {'stage': 'model_response', 'has_content': False, 'has_tool_calls': False}
            )
        sql = extract_sql(raw_content)
        if sql:
            last_sql = sql
        print(f"\n大模型原始输出:\n{raw_content}")
        print(f"\n提取后的SQL:\n{sql}")
        if not sql:
            last_response_error = {
                'stage': 'model_response',
                'response_type': type(message.content).__name__,
                'response_summary': _safe_error_summary(raw_content[:240]),
                'error': '模型响应中未找到SELECT或WITH语句',
            }
            messages.append({
                "role": "user",
                "content": "上一条响应中没有可执行SQL。请立即只输出一条以 SELECT 或 WITH 开头的SQL，不要输出特殊标记或解释。"
            })
            continue

        consistent, consistency_error = check_question_sql_consistency(question, sql)
        if not consistent:
            last_validation_error = consistency_error
            messages.append({
                "role": "user",
                "content": f"生成SQL与题意不一致：{consistency_error}。请修正并只返回SQL。"
            })
            continue

        # 安全检查
        safe, error_msg = check_sql_safety(sql)
        if not safe:
            last_validation_error = error_msg
            print(f"\n[WARN] 安全检查未通过: {error_msg}")
            messages.append({
                "role": "user",
                "content": f"你生成的SQL安全检查未通过，错误信息：{error_msg}。请修正后重新生成SQL，只返回SQL语句。"
            })
            continue
        
        # 执行SQL
        col_names, results, exec_error = execute_sql(sql)
        if exec_error:
            exec_error_count += 1
            print(f"\n[WARN] SQL执行出错（第{exec_error_count}次）: {exec_error}")
            
            if exec_error_count >= SQL_MAX_EXEC_ERRORS:
                print(f"\n[ERROR] 已重试{SQL_MAX_EXEC_ERRORS}次，放弃")
                return fail(
                    'agent_execution_error', exec_error,
                    {'stage': 'sql_execution', 'sql': last_sql, 'error': exec_error},
                )
            
            messages.append({
                "role": "user",
                "content": f"你生成的SQL执行出错，错误信息：{exec_error}。请仔细检查字段名、表名、关联关系、日期格式后修正，只返回SQL语句。"
            })
            continue
        
        print("\n[OK] SQL执行成功！")
        result = AgentResult(sql=sql, columns=col_names, rows=results)
        return result if return_result else result.sql
    
    if last_validation_error:
        return fail(
            'agent_validation_error',
            f'生成的 SQL 未通过安全校验: {last_validation_error}',
            {'stage': 'security_validation', 'error': last_validation_error},
        )
    if last_response_error:
        return fail(
            'agent_generation_error',
            '超过最大 Agent 轮次，模型响应中未找到SELECT或WITH语句',
            last_response_error,
        )
    return fail('agent_generation_error', '超过最大 Agent 轮次仍未生成可执行 SQL')


def execute_sql(sql, validate_sql=True):
    """在独立只读连接中执行 SQL，并限制耗时和返回行数。

    validate_sql=False 仅供评测器执行仓库内的固定基准 SQL 使用；它仍使用只读
    连接、超时和最大返回行数限制，不能用于用户或模型生成的 SQL。
    """
    if validate_sql:
        safe, error_msg = check_sql_safety(sql)
        if not safe:
            return None, None, f"安全检查未通过: {error_msg}"

    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            conn.set_session(readonly=True, autocommit=True)
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = %s", (SQL_STATEMENT_TIMEOUT_MS,))
                cur.execute(sql)
                results = cur.fetchmany(SQL_MAX_RESULT_ROWS + 1)
                if len(results) > SQL_MAX_RESULT_ROWS:
                    return None, None, (
                        f"查询结果超过最大返回行数 {SQL_MAX_RESULT_ROWS}，"
                        "请缩小筛选范围或添加 LIMIT"
                    )
                col_names = [desc[0] for desc in cur.description]
                return col_names, results, None
    except Exception as e:
        return None, None, str(e)


def main():
    print("=" * 60)
    print("取数Agent（带Function Calling版本）")
    print("=" * 60)
    
    # 测试问题
    questions = [
        "查一下客户总数有多少",
        "江苏省的客户有多少个",
        "男性客户的平均年龄是多少",
        "客户等级为钻石卡的客户有多少",
        "总资产排名前10的客户是哪些",
        "总交易金额最高的前5个客户",
    ]
    
    for i, question in enumerate(questions, 1):
        print(f"\n{'='*60}")
        print(f"【问题 {i}】{question}")
        print(f"{'='*60}")
        
        # 运行Agent生成SQL
        result = run_agent(question, return_result=True)
        
        if result:
            print(f"\n✅ 查询成功！")
            print(f"列名：{result.columns}")
            print(f"结果行数：{len(result.rows)}")
            for row in result.rows[:5]:  # 最多显示5行
                print(f"  {row}")
            if len(result.rows) > 5:
                print(f"  ... 共 {len(result.rows)} 行")


if __name__ == "__main__":
    main()
