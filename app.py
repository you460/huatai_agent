import gradio as gr
import pandas as pd
from main import run_agent, execute_sql

# 全局变量：保存查询历史记录
history = []

def answer(question):
    """输入问题，返回生成的SQL、查询结果表格、历史记录"""
    global history
    
    if not question.strip():
        return "请输入问题", pd.DataFrame(), _format_history()
    
    # 1. 调用Agent生成SQL
    sql = run_agent(question)
    
    if not sql:
        return "生成SQL失败，请重试", pd.DataFrame(), _format_history()
    
    # 2. 执行SQL
    col_names, results, error = execute_sql(sql)
    
    if error:
        # 出错也记录到历史（加到末尾，正序）
        history.append({
            "question": question,
            "sql": sql,
            "result": f"执行出错: {error}",
            "row_count": 0
        })
        history = history[-10:]  # 只保留最近10条，超过就删最早的
        return sql, f"执行出错: {error}", _format_history()
    
    # 3. 把结果转成表格
    df = pd.DataFrame(results, columns=col_names)
    
    # 4. 记录到历史（加到末尾，正序）
    history.append({
        "question": question,
        "sql": sql,
        "result": df.to_string(max_rows=5),  # 只显示前5行
        "row_count": len(df)
    })
    history = history[-10:]  # 只保留最近10条
    
    return sql, df, _format_history()

def _format_history():
    """把历史记录格式化成文本显示（正序：最早的在上面）"""
    if not history:
        return "暂无查询记录"
    
    text = ""
    for item in history:
        # 用问题作为每条记录的标题，不编号
        text += f"**❓ {item['question']}**\n\n"
        text += f"```sql\n{item['sql']}\n```\n\n"
        text += f"📊 结果（{item['row_count']}行）：\n```\n{item['result']}\n```\n\n"
        text += "---\n\n"
    
    return text

# 示例问题列表
EXAMPLES = [
    "客户信息表中总共有多少位客户",
    "省份为北京的客户有多少个",
    "按省份统计客户数量，从多到少排序",
    "客户总资产排名前10的客户是哪些",
    "各分公司的客户总资产排名，从高到低",
    "2026年3月各营业部客户总交易金额排名",
]

# 创建界面
with gr.Blocks(title="智能取数Agent") as demo:
    # 标题
    gr.Markdown("# 🔍 智能取数Agent")
    gr.Markdown("输入中文问题，自动生成SQL并查询数据")
    
    gr.Markdown("---")
    
    # 输入区域
    gr.Markdown("### 📝 输入问题")
    question_input = gr.Textbox(
        label="",
        placeholder="请输入你的问题，比如：客户总资产排名前10的客户是哪些？",
        lines=2
    )
    
    # 示例问题按钮
    gr.Markdown("#### 💡 快速试试这些问题：")
    with gr.Row():
        for example in EXAMPLES:
            gr.Button(example, size="sm").click(
                fn=lambda x=example: x,
                outputs=question_input
            )
    
    # 主按钮
    submit_btn = gr.Button("🚀 生成SQL并查询", variant="primary", size="lg")
    
    gr.Markdown("---")
    
    # 当前查询结果区域
    gr.Markdown("### 📄 生成的SQL")
    sql_output = gr.Textbox(label="", lines=5)
    
    gr.Markdown("### 📊 查询结果")
    result_output = gr.Dataframe(label="", wrap=True)
    
    gr.Markdown("---")
    
    # 历史记录区域（折叠起来，默认收起）
    with gr.Accordion("📋 历史查询记录（最近10条）", open=False):
        history_output = gr.Markdown("暂无查询记录")
    
    # 绑定主按钮
    submit_btn.click(
        fn=answer,
        inputs=question_input,
        outputs=[sql_output, result_output, history_output],
        show_progress="minimal"
    )

# 启动界面
if __name__ == "__main__":
    demo.launch()
