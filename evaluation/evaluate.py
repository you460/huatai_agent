import json
import os
import sys
import time
import re
from decimal import Decimal, ROUND_HALF_UP

# Windows 下 stdout 重定向到文件时默认 GBK 编码，无法输出 emoji，统一改为 UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 让 evaluation 子目录能 import 父目录的 main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import run_agent, execute_sql


def _round_half_up(x, nd=2):
    """数值归一化：四舍五入(half-up)到 nd 位，与 SQL 的 round 一致。
    Python 内置 round 是银行家舍入，遇到 .xx5 会与 SQL 差 0.01，导致误判。"""
    try:
        return float(Decimal(str(x)).quantize(Decimal('1e{}'.format(-nd)), rounding=ROUND_HALF_UP))
    except Exception:
        try:
            return float(x)
        except Exception:
            return x


def values_equal(val1, val2):
    """判断两个值是否相等。数值按业务展示口径(2位小数)比较，容忍 ROUND 差异。"""
    if val1 is None and val2 is None:
        return True
    if val1 is None or val2 is None:
        return False
    if hasattr(val1, 'quantize'):
        val1 = float(val1)
    if hasattr(val2, 'quantize'):
        val2 = float(val2)
    if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
        # 标准答案有的 ROUND(,2)、有的保留原值，统一到2位业务精度比较
        if _round_half_up(val1, 2) == _round_half_up(val2, 2):
            return True
        # 四舍五入边界兜底：绝对误差不超过0.01视为相等（不会放过量级不同的值）
        return abs(val1 - val2) <= 0.01
    return val1 == val2


def _rows_equal(row1, row2):
    return len(row1) == len(row2) and all(
        values_equal(value1, value2)
        for value1, value2 in zip(row1, row2)
    )


def _requires_order(question):
    """排名题的返回顺序有业务含义，普通分组题没有。"""
    return bool(re.search(r'排名|前\s*\d+|最高|最低|从高到低|从低到高|降序|升序', question))


def compare_results(col_names1, results1, col_names2, results2, question=''):
    """按完整行比较查询结果；普通分组题允许行顺序不同。"""
    if len(col_names1) != len(col_names2):
        return False
    if any(len(row) != len(col_names1) for row in results1):
        return False
    if any(len(row) != len(col_names2) for row in results2):
        return False
    if not results1 or not results2:
        return not results1 and not results2
    if len(results1) != len(results2):
        return False
    if _requires_order(question):
        return all(_rows_equal(row1, row2) for row1, row2 in zip(results1, results2))

    unmatched_rows = list(results2)
    for row1 in results1:
        for index, row2 in enumerate(unmatched_rows):
            if _rows_equal(row1, row2):
                unmatched_rows.pop(index)
                break
        else:
            return False
    return not unmatched_rows


def is_question_scored(question):
    """题目未标记时默认计分，避免影响现有题库。"""
    return question.get('valid_for_scoring', True)


def parse_question_ids(value):
    """解析可选的逗号分隔题号。"""
    return {int(item.strip()) for item in value.split(',') if item.strip()}


def reviewed_value(question, field):
    """有审核版本时优先使用，官方原内容仍保留在题库中。"""
    return question.get(f'reviewed_{field}', question[field])


def main():
    # 读取测试题
    with open(os.path.join(os.path.dirname(__file__), 'test_questions.json'), 'r', encoding='utf-8') as f:
        questions = json.load(f)

    selected_ids = parse_question_ids(os.environ.get('QUESTION_IDS', ''))
    if selected_ids:
        questions = [q for q in questions if q['id'] in selected_ids]
        result_filename = 'eval_results_subset.json'
        print(f"仅评测题号: {', '.join(map(str, sorted(selected_ids)))}")
    else:
        result_filename = 'eval_results.json'
    
    print(f"共 {len(questions)} 条测试题")
    print("=" * 80)
    
    results = []
    success_count = 0
    invalid_reference_count = 0
    diff_stats = {"简单": {"total": 0, "success": 0}, "中等": {"total": 0, "success": 0}, "较难": {"total": 0, "success": 0}}
    
    for i, q in enumerate(questions, 1):
        question = reviewed_value(q, 'question')
        standard_sql = reviewed_value(q, 'standard_sql')
        print(f"\n[{i}/{len(questions)}] {q['difficulty']} - {question}")
        print("-" * 60)

        # 已审计确认存在业务问题的标准答案，不调用 Agent，也不计入准确率。
        if not is_question_scored(q):
            reason = q.get('reference_note', '题库标记为暂不计分')
            print(f"⚠️ {reason}")
            results.append({
                "id": q['id'],
                "difficulty": q['difficulty'],
                "question": question,
                "success": None,
                "valid_for_scoring": False,
                "reason": reason,
                "generated_sql": None,
                "standard_sql": standard_sql,
                "time": 0
            })
            invalid_reference_count += 1
            continue

        # 先验证标准答案。无效参考题不调用Agent，也不进入准确率分母。
        col_names2, results2, error2 = execute_sql(standard_sql)
        if error2:
            print(f"⚠️ 标准答案SQL执行出错，本题不计分: {error2}")
            results.append({
                "id": q['id'],
                "difficulty": q['difficulty'],
                "question": question,
                "success": None,
                "valid_for_scoring": False,
                "reason": f"标准答案SQL执行出错: {error2}",
                "generated_sql": None,
                "standard_sql": standard_sql,
                "time": 0
            })
            invalid_reference_count += 1
            continue

        start_time = time.time()
        
        # 1. 让Agent生成SQL
        try:
            generated_sql = run_agent(question)
        except Exception as e:
            generated_sql = None
            print(f"❌ Agent调用出错: {e}")
        
        gen_time = time.time() - start_time
        
        if not generated_sql:
            print(f"❌ 生成SQL失败（耗时{gen_time:.1f}s）")
            results.append({
                "id": q['id'],
                "difficulty": q['difficulty'],
                "question": question,
                "success": False,
                "valid_for_scoring": True,
                "reason": "生成SQL失败",
                "generated_sql": None,
                "time": gen_time
            })
            diff_stats[q['difficulty']]["total"] += 1
            continue
        
        # 2. 执行生成的SQL
        col_names1, results1, error1 = execute_sql(generated_sql)
        if error1:
            print(f"❌ 生成的SQL执行出错: {error1}")
            print(f"   生成的SQL: {generated_sql[:100]}...")
            results.append({
                "id": q['id'],
                "difficulty": q['difficulty'],
                "question": question,
                "success": False,
                "valid_for_scoring": True,
                "reason": f"生成SQL执行出错: {error1}",
                "generated_sql": generated_sql,
                "time": gen_time
            })
            diff_stats[q['difficulty']]["total"] += 1
            continue
        
        # 3. 对比结果
        is_correct = compare_results(
            col_names1, results1, col_names2, results2, question
        )
        
        if is_correct:
            print(f"✅ 正确（耗时{gen_time:.1f}s）")
            success_count += 1
            diff_stats[q['difficulty']]["success"] += 1
        else:
            print(f"❌ 结果不一致（耗时{gen_time:.1f}s）")
            print(f"   生成的SQL: {generated_sql[:150]}...")
            print(f"   生成结果前3行: {results1[:3]}")
            print(f"   标准结果前3行: {results2[:3]}")
        
        results.append({
            "id": q['id'],
            "difficulty": q['difficulty'],
            "question": question,
            "success": is_correct,
            "valid_for_scoring": True,
            "reason": "结果一致" if is_correct else "结果不一致",
            "generated_sql": generated_sql,
            "standard_sql": standard_sql,
            "time": gen_time
        })
        diff_stats[q['difficulty']]["total"] += 1
    
    scored_count = len(questions) - invalid_reference_count
    failed_count = scored_count - success_count
    accuracy = success_count / scored_count * 100 if scored_count else 0

    # 输出总结
    print("\n" + "=" * 80)
    print("评测总结")
    print("=" * 80)
    print(f"总题数: {len(questions)}")
    print(f"有效计分题: {scored_count}")
    print(f"无效参考题: {invalid_reference_count}")
    print(f"成功: {success_count}")
    print(f"失败: {failed_count}")
    print(f"整体准确率: {accuracy:.1f}%")
    print()
    
    for diff, stats in diff_stats.items():
        if stats["total"] > 0:
            rate = stats["success"] / stats["total"] * 100
            print(f"{diff}: {stats['success']}/{stats['total']} ({rate:.1f}%)")
    
    # 保存详细结果
    with open(os.path.join(os.path.dirname(__file__), result_filename), 'w', encoding='utf-8') as f:
        json.dump({
            "summary": {
                "total": len(questions),
                "scored": scored_count,
                "invalid_reference": invalid_reference_count,
                "success": success_count,
                "accuracy": accuracy,
                "by_difficulty": diff_stats
            },
            "details": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细结果已保存到 {result_filename}")


if __name__ == "__main__":
    main()
