from openai import OpenAI
import psycopg2
import json
import time
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    LLM_TEMPERATURE, LLM_MAX_RETRIES,
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_CONFIG,
    AGENT_MAX_ROUNDS, SQL_MAX_EXEC_ERRORS
)
from metadata_tools import search_table, get_table_schema, get_metric, METADATA
from security_guard import check_sql_safety

# 初始化大模型客户端
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

# 连接数据库
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

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
- 只返回纯SQL，不加解释文字、不加markdown代码块标记、不重复输出
- 枚举/字典字段：字段摘要里已内嵌枚举取值（如 gender_cd 字典类型500: 取值[5000002=男,...]）。筛选/过滤直接用内嵌代码值（where gender_cd='5000002'），无需 join 字典表；只有展示中文时才 join dim_public，且 code_type_id 必须用摘要里标注的字典类型（如 '500'）。若摘要标注"...共N个"（取值没内嵌全），用模糊匹配（where b.describe like '%医生%'）
- 以下三张维表查询时不要加data_dt条件：dim_branch、dim_product、dim_public；只有dwd_/dws_/ads_开头的事实表才需要加data_dt
- 学历枚举值是"学士""硕士""博士"，不是"本科"；"本科及以上"用 describe IN ('学士','硕士','博士')
- 只返回问题明确需要的列，不要返回额外统计列（问"平均年龄"就只返回平均年龄，不返回count）
- 查询"前N的客户"等排名/列表类问题时，返回 pty_id（客户号，不用 name）、排名依据的数值列（如交易金额、总资产）、以及题目要求的属性列
- 产品分类：一级分类用 up_prdt_type_name，二级分类用 prdt_type_name。"债券"是一级分类(up_prdt_type_name='债券')，"A股/科创板/ETF"是二级分类(prdt_type_name='A股'等)；不要用 prdt_name/prdt_type_name LIKE '%债%' 表示债券，会误纳"交易型债券ETF"等开放式基金
- 统计"各营业部"要同时返回分公司名(up_org_name)和营业部名(org_name)
- 月份与季度区分：问"X月"指该自然月（"3月"= data_dt between '20260301' and '20260331'），问"Q1"才是季度（between '20260101' and '20260331'），两者不要混用
- 年龄段默认：<30、[30,50)、[50,60)、[60,)
- "普通客户"指客户等级"紫金理财卡客户"(cust_lvl_cd='1000005')，即基础理财卡，不是"非钻石卡客户"；不要用 describe like '%普通%' 或 NOT LIKE '%钻石卡%' 表示（字典里没有"普通"字样）
- 计算"平均持仓市值/平均持仓金额"：先在子查询按 pty_id 对 mkt_val 求和（一个客户可能持多只产品），再外层 AVG，不要直接 AVG(mkt_val)；且用 LEFT JOIN + coalesce(...,0) 包含所有客户，不要用 INNER JOIN 只统计有持仓的
- 关联不同表不要在 join 条件里加 data_dt 相等，各表在 where 里各自过滤分区
- 佣金率/占比/比率类指标返回小数（0.001 表示 0.1%），不要乘100

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
    return text


def call_llm(messages):
    """调用大模型，失败自动重试，返回response或None"""
    for retry in range(LLM_MAX_RETRIES):
        try:
            return client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=LLM_TEMPERATURE
            )
        except Exception as e:
            if retry < LLM_MAX_RETRIES - 1:
                print(f"大模型调用失败（第{retry+1}次）: {str(e)[:100]}，重试中...")
                time.sleep(1)
            else:
                print(f"大模型调用失败，已重试{LLM_MAX_RETRIES}次: {str(e)[:100]}")
    return None


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


def run_agent(question):
    """运行Agent，带Function Calling和SQL执行错误自动修正"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question}
    ]
    
    exec_error_count = 0
    tool_cache = {}
    
    for round_num in range(AGENT_MAX_ROUNDS):
        print(f"\n--- 第 {round_num+1} 轮大模型调用 ---")
        
        response = call_llm(messages)
        if not response:
            return None
        
        message = response.choices[0].message
        messages.append(message)
        
        # 处理工具调用
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_result, _ = execute_tool_call(tool_call, tool_cache)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })
                print(f"工具返回结果: {json.dumps(tool_result, ensure_ascii=False)[:200]}...")
            continue
        
        # 模型返回最终 SQL
        raw_content = message.content.strip()
        sql = extract_sql(raw_content)
        print(f"\n大模型原始输出:\n{raw_content}")
        print(f"\n提取后的SQL:\n{sql}")
        
        # 安全检查
        safe, error_msg = check_sql_safety(sql)
        if not safe:
            print(f"\n⚠️ 安全检查未通过: {error_msg}")
            messages.append({
                "role": "user",
                "content": f"你生成的SQL安全检查未通过，错误信息：{error_msg}。请修正后重新生成SQL，只返回SQL语句。"
            })
            continue
        
        # 执行SQL
        col_names, results, exec_error = execute_sql(sql)
        if exec_error:
            exec_error_count += 1
            print(f"\n⚠️ SQL执行出错（第{exec_error_count}次）: {exec_error}")
            
            if exec_error_count >= SQL_MAX_EXEC_ERRORS:
                print(f"\n❌ 已重试{SQL_MAX_EXEC_ERRORS}次，放弃")
                return None
            
            messages.append({
                "role": "user",
                "content": f"你生成的SQL执行出错，错误信息：{exec_error}。请仔细检查字段名、表名、关联关系、日期格式后修正，只返回SQL语句。"
            })
            continue
        
        print(f"\n✅ SQL执行成功！")
        return sql
    
    return None


def execute_sql(sql):
    """执行SQL并返回结果，连接断开时自动重连"""
    global conn, cur
    try:
        # 检查连接是否正常，断开则重连
        if conn.closed:
            print("数据库连接断开，正在重连...")
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
        
        cur.execute(sql)
        results = cur.fetchall()
        col_names = [desc[0] for desc in cur.description]
        conn.commit()
        return col_names, results, None
    except psycopg2.InterfaceError as e:
        # 连接异常，重连一次
        print(f"数据库连接异常: {e}，正在重连...")
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute(sql)
            results = cur.fetchall()
            col_names = [desc[0] for desc in cur.description]
            conn.commit()
            return col_names, results, None
        except Exception as e2:
            conn.rollback()
            return None, None, str(e2)
    except Exception as e:
        conn.rollback()
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
        sql = run_agent(question)
        
        if sql:
            # 执行SQL
            col_names, results, error = execute_sql(sql)
            
            if error:
                print(f"\n❌ 执行出错：{error}")
            else:
                print(f"\n✅ 查询成功！")
                print(f"列名：{col_names}")
                print(f"结果行数：{len(results)}")
                for row in results[:5]:  # 最多显示5行
                    print(f"  {row}")
                if len(results) > 5:
                    print(f"  ... 共 {len(results)} 行")
    
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
