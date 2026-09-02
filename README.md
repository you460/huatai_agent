# 智能取数 Agent
# 1
客户营销场景下的自然语言取数系统。业务人员用中文提问，系统自动生成 SQL、执行并返回结果，不用写代码也能查数据。

## 功能

- **自然语言问数**：输入中文问题，自动拆解意图、生成 PostgreSQL SQL 并执行
- **元数据检索**：通过工具调用让模型按需查表、查字段、查指标，而不是把全库结构塞给模型
- **安全围栏**：只允许 SELECT，校验表名、字段名和语法，拦截危险操作
- **Web 图形界面**：Gradio 前端，输入中文问题即可查询，结果表格化展示
- **自动化评测**：150 道分级测试题，一键跑出准确率报告

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
│   ├── test_questions.json
│   └── eval_results.json
├── requirements.txt     # 依赖
└── .env.example         # 配置模板
```

## 环境要求

- Python 3.10+
- PostgreSQL（已建库并导入数据，库名默认 `huatai`）

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
from main import run_agent, execute_sql

sql = run_agent("男性客户有多少个")
cols, rows, err = execute_sql(sql)
print(cols, rows)
```

## 评测

```bash
python evaluation/evaluate.py
```

脚本会跑完 `evaluation/test_questions.json` 里的 150 道题，逐题对比生成结果和标准答案，最后输出按难度的准确率，并把明细写进 `evaluation/eval_results.json`。无法执行的标准 SQL 会标记为无效参考题，不计入准确率分母。

## 安全说明

系统只允许 SELECT 查询，DROP / DELETE / UPDATE 等操作会被安全围栏拦截。提交代码时 `.env` 不会被包含（已加入 `.gitignore`）。
