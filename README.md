# 智能取数 Agent

客户营销场景下的自然语言取数系统。业务人员用中文提问，系统自动生成 SQL、执行并返回结果，不用写代码也能查数据。

## 功能

- 自然语言问数：输入中文问题，自动拆解意图、生成 PostgreSQL SQL 并执行
- 元数据检索：通过工具调用让模型按需查表、查字段、查指标，而不是把全库结构塞给模型
- 安全围栏：只允许 SELECT，校验表名、字段名和语法，拦截危险操作
- Web 图形界面：Gradio 前端，输入中文问题即可查询，结果表格化展示
- 自动化评测：官方7题、30题泛化集、固定90题主回归集分别输出可信度报告，并保留150题完整回归入口

## 技术栈

- Python 3.10
- DeepSeek API（OpenAI 协议）
- PostgreSQL
- sqlglot（SQL 解析校验）
- Gradio（Web 界面）

## 目录结构

```
huatai_agent/
├── app.py               # Gradio Web 界面
├── main.py              # Agent 主流程
├── metadata_tools.py    # 元数据检索
├── security_guard.py    # 安全围栏
├── config.py            # 配置
├── metadata/
│   └── metadata.json    # 元数据：表结构、字段、枚举、关联关系、业务指标
├── evaluation/          # 评测（独立目录）
│   ├── evaluate.py      # 评测脚本
│   ├── test_questions.json             # 原150题与基准SQL
│   ├── generalization_questions.json   # 30道独立改写题
│   ├── field_contracts.json            # 字段语义与排序合同
│   ├── suites.json                     # 固定评测集定义
│   ├── data_snapshot_manifest.json      # 数据快照行数、分区和结构清单
│   ├── snapshot_manifest.py             # 生成或核验数据库快照
│   ├── summarize_runs.py                # 汇总多次评测的均值与波动
│   ├── build_questions.py              # 原题库构建工具
│   ├── build_generalization_questions.py # 泛化题构建工具
│   ├── eval_results_v2_official7_<timestamp>.json
│   ├── eval_results_v2_generalization30_<timestamp>.json
│   └── eval_results_v2_compact90_<timestamp>.json
├── tests/                # 单元与回归测试
├── requirements.txt     # 兼容依赖范围
├── requirements-lock.txt # 当前正式评测的直接依赖精确版本
└── .env.example         # 配置模板
```

## 环境要求

- Python 3.10+
- PostgreSQL（已建库并导入数据，库名默认 `huatai`）

当前正式评测使用 Python 3.12。`requirements.txt` 适合日常安装；需要尽量贴近当前评测环境时，使用记录了直接依赖精确版本的 `requirements-lock.txt`。

数据集共 8 张表：

| 表 | 说明 |
|---|---|
| ads_cust_info_d | 客户信息快照 |
| dim_product | 产品维度 |
| dim_branch | 营业部 |
| dim_public | 编码字典 |
| dwd_cust_hold_d | 客户持仓 |
| dwd_cust_tran_d | 客户交易 |
| dws_cust_aset_d | 客户资产 |
| dws_cust_fin_d | 客户资金流水 |

## 安装

```bash
pip install -r requirements.txt
```

复现当前评测环境：

```bash
pip install -r requirements-lock.txt
```

## 配置

复制 `.env.example` 为 `.env`，填入自己的值：

```bash
cp .env.example .env
```

`.env` 里需要两项：

- `DEEPSEEK_API_KEY`：DeepSeek 的 API key（申请地址 https://platform.deepseek.com/）
- `DB_PASSWORD`：PostgreSQL 密码

其余项（数据库地址、模型名等）有默认值，一般不用改。

## 运行

Web 图形界面（推荐）：

```bash
python app.py
```

浏览器打开启动时打印的本地地址即可，输入中文问题会自动生成 SQL 并展示结果。

单次查询：

```bash
python main.py
```

`main.py` 末尾有一个示例问题列表，改成自己想问的问题即可。也可以直接在代码里调用：

```python
from main import run_agent

result = run_agent("男性客户有多少个", return_result=True)
print(result.columns, result.rows)
```

## 评测

```bash
# 默认运行固定精简回归集：90题，每个难度30题，包含全部7道官方样例
python evaluation/evaluate.py

# 单独观察7道官方Q&A样例
python evaluation/evaluate.py --suite official7

# 独立运行30道同义改写泛化题，成绩与回归集分开报告
python evaluation/evaluate.py --suite generalization30

# 需要时运行历史完整150题回归集
python evaluation/evaluate.py --suite full150
```

评测集定义保存在 `evaluation/suites.json`。默认的 `compact90` 按题号全区间固定等距抽取，不依据模型历史得分挑题；原150题和基准SQL继续保留。当前正式依据由最新的 `official7`、`generalization30` 和 `compact90` 三份结果组成。报告分别记录 `value_match`、`schema_match`、`overall_success`、难度分层、官方/自建来源表现和平均Agent耗时，并按时间戳生成新文件，便于每轮完成后替换旧输出。

这90题属于内部回归基准。7道 `source=official` 的题目来自官方Q&A示例，只能说明对公开样例的兼容性，不能代表官方隐藏测试成绩。`generalization30`复用基础题的基准SQL，但改写自然语言表达，并按改写类型单独统计；它用于观察表达泛化，不能替代官方隐藏测试。泛化题一旦开始用于调整提示词，就应冻结并另建新的留出集。

字段语义合同保存在 `evaluation/field_contracts.json`。可为指定题号配置预期语义、允许别名和排序规则；未显式配置的题目会从基准 SQL 返回列生成默认合同。排名题默认允许同一主排序值的行互换顺序；若业务要求固定并列顺序，需要在合同中设为 `fixed`，并让两侧 SQL 都声明二级 `ORDER BY`。

## 复现评测

评测前先确认数据库与项目记录的快照一致：

```bash
python evaluation/snapshot_manifest.py --verify
```

`evaluation/evaluate.py` 默认也会在调用模型前自动执行同一核验；若数据库不一致，评测会直接停止。`EVALUATION_VERIFY_SNAPSHOT=0` 只应用于明确知道数据差异的本地调试，不能用于可比较的正式成绩。

首次在受控环境建立快照清单时使用 `--write`。该清单只保存8张表的行数、分区边界和数据库实际字段结构哈希，不保存客户明细：

```bash
python evaluation/snapshot_manifest.py --write
```

每份新版报告会记录 Python和操作系统版本、直接依赖版本、模型参数、提示词版本及哈希、题库与关键元数据哈希、Git状态、核心代码快照哈希和数据库快照清单哈希。API Key只用于鉴权，不写入报告。

大模型即使在温度为0时也可能有轻微波动。正式报告建议在代码、数据和配置完全相同时连续运行3次，再汇总同一套评测结果：

```bash
python evaluation/summarize_runs.py evaluation/eval_results_v2_compact90_<运行1>.json evaluation/eval_results_v2_compact90_<运行2>.json evaluation/eval_results_v2_compact90_<运行3>.json --output evaluation/compact90_stability.json
```

汇总工具只接受题库、数据快照、提示词、代码和判分规则完全一致的报告，并输出 `value_match`、`schema_match`、`overall_success` 的平均值、最低值、最高值和波动范围。公开成绩时应同时报告运行次数、平均准确率和最低准确率。

快照清单能发现表行数、日期范围或数据库结构变化，但不是逐行业务数据全文哈希。若官方同时提供原始数据文件，还应在提交说明中记录官方文件自身的 SHA-256；项目不复制或重新发布无授权的数据文件。

## 安全说明

系统只允许只读 SELECT / WITH 查询，危险函数、写操作和无 `LIMIT` 的明细查询会被安全围栏拦截。每次查询使用独立只读数据库连接，默认超时为 10 秒、最多返回 5000 行；可通过 `.env` 中的 `SQL_STATEMENT_TIMEOUT_MS` 和 `SQL_MAX_RESULT_ROWS` 调整。聚合统计不会被自动加 `LIMIT`，计算口径不受展示行数限制影响。提交代码时 `.env` 不会被包含（已加入 `.gitignore`）。
