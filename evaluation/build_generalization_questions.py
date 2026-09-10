"""构建独立的同义改写评测集。

只复用原题的业务语义和基准 SQL，不修改 test_questions.json。
改写题不参与提示词和规则调优时，才可作为泛化观察指标。
"""
import json
from pathlib import Path


VARIANTS = [
    (1, '请统计最新客户快照中的客户总人数', 'synonym'),
    (2, '最新客户名单里，男性一共有多少人', 'word_order'),
    (5, '客户等级为白金卡的一共有多少人', 'synonym'),
    (9, '还不到30岁的客户共有几位', 'boundary_expression'),
    (13, '客户归属省份为江苏省的有多少人', 'word_order'),
    (20, 'A股这一产品子类总共有多少只产品', 'business_term'),
    (25, '截至2026年一季度末，全市场客户持仓市值合计是多少', 'time_expression'),
    (29, '最新快照下客户年龄的均值是多少', 'metric_expression'),
    (37, '男性客户中年龄至少达到50岁的有多少人', 'boundary_expression'),
    (45, '一季度末普通账户现金资产超过10万元的客户数', 'time_expression'),
    (51, '男性中学历至少为学士且年龄超过50岁的人数', 'condition_reorder'),
    (55, '按性别分别统计客户人数', 'synonym'),
    (61, '一季度每位客户累计成交金额是多少', 'metric_expression'),
    (67, '每个分公司下设多少个营业部', 'word_order'),
    (72, '分别汇总普通系统来源和信用系统来源在一季度的成交额', 'business_term'),
    (77, '各分公司客户人数由高到低排列', 'ranking_expression'),
    (82, '按产品子类对一季度成交额进行排名', 'business_term'),
    (89, '一季度末持有ETF的客户共有多少人', 'time_expression'),
    (95, '按学历层次统计男性客户人数', 'synonym'),
    (100, '按营业部统计客户一季度成交额并进行排名', 'ranking_expression'),
    (101, '筛选年龄超过40岁的钻石卡男性、比亚迪持仓市值累计超1000元的客户，给出其2026年一季度盈亏情况明细', 'condition_reorder'),
    (102, '找出2026年一季度交易过招商银行，同时季末普通账户持有中国平安的客户', 'condition_reorder'),
    (133, '按省份统计2026年一季度创业板累计成交额超过20万元的客户人数', 'condition_reorder'),
    (104, '统计2026年1月10日至2月15日科创板累计成交额超25万元客户的营业部分布', 'time_expression'),
    (116, '2026年一季度发生过资金转入、但期末不存在正资产的客户数', 'negative_condition'),
    (121, '客户平均总资产最高的十个营业部', 'ranking_expression'),
    (134, '按分公司给出钻石卡客户所占比例', 'projection_expression'),
    (143, '以实际持仓产品一级类别统计客户覆盖率', 'business_term'),
    (145, '计算女性客户人均持仓市值减去男性客户人均持仓市值', 'metric_expression'),
    (150, '季末持有ETF且一季度发生过任意产品交易的客户数', 'condition_scope'),
]


def main():
    folder = Path(__file__).resolve().parent
    source = json.loads((folder / 'test_questions.json').read_text(encoding='utf-8'))
    by_id = {item['id']: item for item in source}
    output = []
    if len(VARIANTS) != 30 or len({item[0] for item in VARIANTS}) != 30:
        raise ValueError('泛化集必须包含30个不同的基础题')
    for index, (base_id, question, variant_type) in enumerate(VARIANTS, 1001):
        base = by_id[base_id]
        if question.strip() == base['question'].strip():
            raise ValueError(f'基础题 {base_id} 没有发生改写')
        output.append({
            'id': index,
            'base_id': base_id,
            'difficulty': base['difficulty'],
            'question': question,
            'standard_sql': base.get('reviewed_standard_sql') or base['standard_sql'],
            'source': 'generalization',
            'variant_type': variant_type,
        })
    (folder / 'generalization_questions.json').write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(f'已生成 generalization_questions.json，共 {len(output)} 题')


if __name__ == '__main__':
    main()
