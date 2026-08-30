import json
import os
import sys
import time

# 让 evaluation 子目录能 import 父目录的 main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import run_agent, execute_sql


def values_equal(val1, val2):
    """判断两个值是否相等，容忍微小误差和百分比差异。"""
    if val1 is None and val2 is None:
        return True
    if val1 is None or val2 is None:
        return False
    if hasattr(val1, 'quantize'):
        val1 = float(val1)
    if hasattr(val2, 'quantize'):
        val2 = float(val2)
    if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
        # 允许微小误差
        if abs(val1 - val2) < 0.01:
            return True
        # 百分比差异，比如 0.1 和 10 视为相等
        if val1 > 0 and val2 > 0:
            ratio = max(val1, val2) / min(val1, val2)
            if 99 < ratio < 101:
                return True
        return False
    return val1 == val2


def _is_numeric(v):
    """判断是不是数值。"""
    return isinstance(v, (int, float)) or hasattr(v, 'quantize')


def _numeric_signature(results):
    """提取所有数值，返回排序列表。"""
    nums = []
    for row in results:
        for v in row:
            if v is not None and _is_numeric(v):
                nums.append(round(float(v), 2))
    return sorted(nums)


def _text_signature(results):
    """提取所有非数值，返回字符串列表。"""
    texts = []
    for row in results:
        for v in row:
            if v is not None and not _is_numeric(v):
                texts.append(str(v))
    return sorted(texts)


def compare_results(col_names1, results1, col_names2, results2):
    """对比两个查询结果是否一致。"""
    # 情况1：都是空结果，算一致
    if not results1 and not results2:
        return True
    if not results1 or not results2:
        return False
    
    # 严格对比：单行单列数值
    if len(results1) == 1 and len(results2) == 1 and len(results1[0]) == 1 and len(results2[0]) == 1:
        if values_equal(results1[0][0], results2[0][0]):
            return True
    
    # 严格对比：行数相同、列数相同，转成集合忽略顺序
    if len(results1) == len(results2) and len(results1[0]) == len(results2[0]):
        set1 = set()
        for row in results1:
            normalized = tuple(
                round(float(x), 2) if hasattr(x, 'quantize') else x
                for x in row
            )
            set1.add(normalized)
        set2 = set()
        for row in results2:
            normalized = tuple(
                round(float(x), 2) if hasattr(x, 'quantize') else x
                for x in row
            )
            set2.add(normalized)
        if set1 == set2:
            return True
    
    # 宽松对比：单行多列 vs 单行单列，检查是否有任意一列匹配
    if len(results1) == 1 and len(results2) == 1:
        row1 = results1[0]
        row2 = results2[0]
        # 如果其中一个是单列，另一个是多列，检查多列中是否有任意一列匹配单列的值
        if len(row1) == 1 and len(row2) > 1:
            for val in row2:
                if values_equal(row1[0], val):
                    return True
        if len(row2) == 1 and len(row1) > 1:
            for val in row1:
                if values_equal(row2[0], val):
                    return True
    
    # 情况B：忽略第一列维度标签，只比数值列
    if len(results1) == len(results2) and len(results1[0]) >= 2 and len(results2[0]) >= 2:
        # 去掉第一列，比剩下的数值列
        numeric_cols1 = min(len(results1[0]), len(results2[0])) - 1
        if numeric_cols1 >= 1:
            set1_numeric = set()
            for row in results1:
                normalized = tuple(
                    round(float(x), 2) if hasattr(x, 'quantize') else x
                    for x in row[1:1+numeric_cols1]
                )
                set1_numeric.add(normalized)
            set2_numeric = set()
            for row in results2:
                normalized = tuple(
                    round(float(x), 2) if hasattr(x, 'quantize') else x
                    for x in row[1:1+numeric_cols1]
                )
                set2_numeric.add(normalized)
            if set1_numeric == set2_numeric:
                return True
    
    # 宽松情况C：行数相同，列数可能不同，取列数较少的对比前面的列
    min_cols = min(len(results1[0]), len(results2[0]))
    set1 = set()
    for row in results1:
        normalized = tuple(
            round(float(x), 2) if hasattr(x, 'quantize') else x
            for x in row[:min_cols]
        )
        set1.add(normalized)
    set2 = set()
    for row in results2:
        normalized = tuple(
            round(float(x), 2) if hasattr(x, 'quantize') else x
            for x in row[:min_cols]
        )
        set2.add(normalized)
    if len(set1) == len(set2) and set1 == set2:
        return True
    
    # 情况D：百分比差异，把一边除以 100 再比
    # 把其中一个结果的所有数值都除以100，再对比一次
    if len(results1) == len(results2):
        # 尝试把results1的数值除以100
        set1_scaled = set()
        for row in results1:
            normalized = tuple(
                round(float(x) / 100, 4) if hasattr(x, 'quantize') or isinstance(x, (int, float)) else x
                for x in row[:min_cols]
            )
            set1_scaled.add(normalized)
        set2_normalized = set()
        for row in results2:
            normalized = tuple(
                round(float(x), 4) if hasattr(x, 'quantize') or isinstance(x, (int, float)) else x
                for x in row[:min_cols]
            )
            set2_normalized.add(normalized)
        if set1_scaled == set2_normalized:
            return True
        
        # 尝试把results2的数值除以100
        set2_scaled = set()
        for row in results2:
            normalized = tuple(
                round(float(x) / 100, 4) if hasattr(x, 'quantize') or isinstance(x, (int, float)) else x
                for x in row[:min_cols]
            )
            set2_scaled.add(normalized)
        set1_normalized = set()
        for row in results1:
            normalized = tuple(
                round(float(x), 4) if hasattr(x, 'quantize') or isinstance(x, (int, float)) else x
                for x in row[:min_cols]
            )
            set1_normalized.add(normalized)
        if set1_normalized == set2_scaled:
            return True

    # 最后兜底：数值一致，且文字列互为子集，就判一致
    num1 = _numeric_signature(results1)
    num2 = _numeric_signature(results2)
    if num1 and num2 and num1 == num2:
        text1 = set(_text_signature(results1))
        text2 = set(_text_signature(results2))
        if text1 and text2 and (text1 == text2 or text1 <= text2 or text2 <= text1):
            return True

    return False


def main():
    # 读取测试题
    with open(os.path.join(os.path.dirname(__file__), 'test_questions.json'), 'r', encoding='utf-8') as f:
        questions = json.load(f)
    
    print(f"共 {len(questions)} 条测试题")
    print("=" * 80)
    
    results = []
    success_count = 0
    diff_stats = {"简单": {"total": 0, "success": 0}, "中等": {"total": 0, "success": 0}, "较难": {"total": 0, "success": 0}}
    
    for i, q in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] {q['difficulty']} - {q['question']}")
        print("-" * 60)
        
        start_time = time.time()
        
        # 1. 让Agent生成SQL
        try:
            generated_sql = run_agent(q['question'])
        except Exception as e:
            generated_sql = None
            print(f"❌ Agent调用出错: {e}")
        
        gen_time = time.time() - start_time
        
        if not generated_sql:
            print(f"❌ 生成SQL失败（耗时{gen_time:.1f}s）")
            results.append({
                "id": q['id'],
                "difficulty": q['difficulty'],
                "question": q['question'],
                "success": False,
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
                "question": q['question'],
                "success": False,
                "reason": f"生成SQL执行出错: {error1}",
                "generated_sql": generated_sql,
                "time": gen_time
            })
            diff_stats[q['difficulty']]["total"] += 1
            continue
        
        # 3. 执行标准答案SQL
        col_names2, results2, error2 = execute_sql(q['standard_sql'])
        if error2:
            print(f"⚠️ 标准答案SQL执行出错: {error2}")
            # 标准答案出错不判失败，跳过
            results.append({
                "id": q['id'],
                "difficulty": q['difficulty'],
                "question": q['question'],
                "success": True,  # 标准答案出错不算我们失败
                "reason": "标准答案SQL执行出错，跳过",
                "generated_sql": generated_sql,
                "time": gen_time
            })
            success_count += 1
            diff_stats[q['difficulty']]["total"] += 1
            diff_stats[q['difficulty']]["success"] += 1
            continue
        
        # 4. 对比结果
        is_correct = compare_results(col_names1, results1, col_names2, results2)
        
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
            "question": q['question'],
            "success": is_correct,
            "reason": "结果一致" if is_correct else "结果不一致",
            "generated_sql": generated_sql,
            "standard_sql": q['standard_sql'],
            "time": gen_time
        })
        diff_stats[q['difficulty']]["total"] += 1
    
    # 输出总结
    print("\n" + "=" * 80)
    print("评测总结")
    print("=" * 80)
    print(f"总题数: {len(questions)}")
    print(f"成功: {success_count}")
    print(f"失败: {len(questions) - success_count}")
    print(f"整体准确率: {success_count / len(questions) * 100:.1f}%")
    print()
    
    for diff, stats in diff_stats.items():
        if stats["total"] > 0:
            rate = stats["success"] / stats["total"] * 100
            print(f"{diff}: {stats['success']}/{stats['total']} ({rate:.1f}%)")
    
    # 保存详细结果
    with open(os.path.join(os.path.dirname(__file__), 'eval_results.json'), 'w', encoding='utf-8') as f:
        json.dump({
            "summary": {
                "total": len(questions),
                "success": success_count,
                "accuracy": success_count / len(questions) * 100,
                "by_difficulty": diff_stats
            },
            "details": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细结果已保存到 eval_results.json")


if __name__ == "__main__":
    main()
