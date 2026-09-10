import gradio as gr
import pandas as pd
from main import AgentResult, run_agent

def answer(question, history):
    """输入问题，返回生成的SQL、查询结果表格、历史记录"""
    history = list(history or [])
    
    if not question.strip():
        return "请输入问题", pd.DataFrame(), _format_history(history), history
    
    # 1. 调用Agent生成SQL
    agent_result = run_agent(question, return_result=True)
    
    if not isinstance(agent_result, AgentResult):
        reason = getattr(agent_result, "message", None) or "Agent 未返回可用结果"
        return f"生成SQL失败：{reason}", pd.DataFrame(), _format_history(history), history
    
    # Agent 已执行并验证过 SQL；界面直接复用该结果，避免第二次查询。
    df = pd.DataFrame(agent_result.rows, columns=agent_result.columns)
    
    # 4. 记录到历史（加到末尾，正序）
    history.append({
        "question": question,
        "sql": agent_result.sql,
        "result": df.to_string(max_rows=5),  # 只显示前5行
        "row_count": len(df)
    })
    history = history[-10:]  # 只保留最近10条
    
    return agent_result.sql, df, _format_history(history), history

def _format_history(history):
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
    session_history = gr.State([])
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
        inputs=[question_input, session_history],
        outputs=[sql_output, result_output, history_output, session_history],
        show_progress="minimal"
    )

# 启动界面
if __name__ == "__main__":
    demo.launch()
