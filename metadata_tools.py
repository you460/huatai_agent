import json
import os

# 读取元数据JSON
METADATA_PATH = os.path.join(os.path.dirname(__file__), 'metadata', 'metadata.json')
with open(METADATA_PATH, 'r', encoding='utf-8') as f:
    METADATA = json.load(f)

TABLES = METADATA['tables']

BUSINESS_RULE_TRIGGERS = {
    'product_name_grouping': (r'每个产品', r'各产品', r'按产品(?:名称|名字)', r'产品.*汇总'),
    'branch_grouping': (r'营业部.*(?:统计|汇总|排名|分布)', r'各营业部', r'每个营业部'),
    'stock_category': (r'股票(?:交易|持仓|产品)', r'股票.*(?:金额|数量|客户)'),
    'no_positive_asset': (r'(?:没有|无|不存在).*正资产', r'资产.*(?:不大于|<=)\s*0'),
    'ratio_projection': (r'占比', r'比率', r'渗透率'),
    'average_asset_population': (r'平均总资产', r'总资产.*平均', r'人均总资产'),
    'independent_conditions': (r'持有.*且.*有交易', r'持仓.*同时.*发生交易'),
    'snapshot_join_dates': (r'(?:客户|资产|持仓|交易).*(?:日期|快照|期间)', r'\d{4}年.*(?:客户|资产|持仓|交易)'),
    'distribution_projection': (r'(?:资产|金额|市值)分布', r'分布.*(?:资产|金额|市值)'),
    'computed_column_alias': (r'差值', r'占比|比率|渗透率', r'平均|总额|数量'),
    'product_category_output': (r'属于哪些.*(?:产品)?大类', r'持有.*产品.*(?:大类|分类)'),
    'explicit_product_category_level': (r'产品一级分类', r'产品二级分类', r'按一级分类', r'按二级分类'),
    'product_penetration_population': (r'产品.*(?:分类)?.*渗透率', r'渗透率.*产品.*分类'),
    'average_holding_population': (r'平均持仓(?:市值|金额)', r'持仓(?:市值|金额).*平均'),
    'inclusive_age_wording': (r'\d+岁(?:及)?以上', r'年龄在\d+岁以上', r'\d+岁(?:及)?以下'),
    'customer_ranking_column_order': (r'(?:客户|客户号).*(?:前\s*\d+|排名)', r'(?:前\s*\d+|排名).*客户'),
    'customer_region_distribution': (r'客户.*(?:省份|城市|地域)分布', r'(?:省份|城市|地域).*客户.*分布'),
    'difference_only_projection': (r'差值', r'之差|相差'),
    'branch_join_key': (r'营业部.*(?:交易|买入|卖出|金额)', r'(?:交易|买入|卖出|金额).*营业部'),
    'ratio_query_optimisation': (
        r'持仓市值.*总资产.*(?:占比|比例|%)', r'持仓.*大于.*总资产',
        r'持仓.*(?:占|比例).*总资产',
    ),
}

# 枚举值缓存，key 是字典类型 code_type_id
_ENUM_CACHE = None
_ENUM_MAX_PER_FIELD = 10  # 枚举值最多内嵌几个


def _load_enum_cache():
    """从 dim_public 读枚举值并缓存。"""
    global _ENUM_CACHE
    if _ENUM_CACHE is not None:
        return _ENUM_CACHE
    cache = {}
    try:
        import psycopg2
        from config import DB_CONFIG
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT code_type_id, code, describe FROM dim_public")
        for code_type_id, code, desc in cur.fetchall():
            cache.setdefault(code_type_id, {})[code] = desc
        conn.close()
    except Exception as e:
        print(f"枚举值加载失败: {str(e)[:80]}")
    _ENUM_CACHE = cache
    return cache


def _format_column(col):
    """把一个字段压成一行摘要。"""
    name = col.get('column_name', '')
    cn = col.get('column_cn_name', '')
    s = f"{name}({cn})"

    # 枚举字段，带上取值
    if col.get('is_enum'):
        if col.get('enum_source') == 'inline':
            vals = col.get('enum_values', [])
            if vals:
                enum_str = ', '.join(f"{v['value']}={v['desc']}" for v in vals)
                s += f" 取值[{enum_str}]"
        elif col.get('enum_source') == 'dim_public':
            type_id = col.get('enum_type_id', '')
            enums = _load_enum_cache().get(type_id, {})
            if enums:
                items = list(enums.items())[:_ENUM_MAX_PER_FIELD]
                enum_str = ', '.join(f"{k}={v}" for k, v in items)
                more = f", ...共{len(enums)}个" if len(enums) > _ENUM_MAX_PER_FIELD else ""
                s += f" 字典类型{type_id}: 取值[{enum_str}{more}]"
            else:
                s += f" [枚举: join dim_public where code_type_id='{type_id}']"

    # 关联键，标注目标表
    if col.get('is_join_key'):
        s += f" [关联键→{col.get('related_table', '')}]"

    return s


def _build_table_summary(table):
    """生成一张表的摘要。"""
    return {
        "table_name": table.get('table_name'),
        "table_cn_name": table.get('table_cn_name'),
        "table_desc": table.get('table_description'),
        "partition_key": table.get('partition_key', ''),
        "columns": [_format_column(c) for c in table.get('columns', [])],
    }


def search_table(keyword):
    """按关键词搜表，返回表信息和字段摘要。"""
    results = []
    keyword_lower = keyword.lower()

    for table in TABLES:
        table_name = table.get('table_name', '').lower()
        table_cn_name = table.get('table_cn_name', '')
        table_desc = table.get('table_description', '')
        columns_text = ''
        for col in table.get('columns', []):
            columns_text += col.get('column_name', '') + col.get('column_cn_name', '') + col.get('column_description', '')

        if (keyword_lower in table_name or keyword in table_cn_name or
                keyword in table_desc or keyword in columns_text):
            results.append(_build_table_summary(table))

    return results


def get_table_schema(table_name):
    """返回单张表的完整字段信息。"""
    for table in TABLES:
        if table.get('table_name') == table_name:
            return table
    return None


def get_metric(keyword):
    """按关键词搜业务指标。"""
    metrics = METADATA.get('business_metrics', [])
    results = []
    keyword_lower = keyword.lower()

    for metric in metrics:
        metric_name = metric.get('metric_name', '')
        metric_desc = metric.get('metric_desc', '')
        metric_formula = metric.get('metric_formula', '')

        if (keyword in metric_name or keyword in metric_desc or
                keyword_lower in metric_formula.lower()):
            results.append(metric)

    return results


def match_business_rules(question):
    """按题意同义表达返回适用的通用业务规则，供提示词和测试复用。"""
    import re
    matched = {}
    rules = METADATA.get('global_rules', {})
    for rule_name, patterns in BUSINESS_RULE_TRIGGERS.items():
        if rule_name in rules and any(re.search(pattern, question, re.IGNORECASE) for pattern in patterns):
            matched[rule_name] = rules[rule_name]
    return matched


if __name__ == '__main__':
    import json as _json
    print("=== search_table('客户') 字段摘要 ===")
    for r in search_table('客户'):
        print(f"\n表: {r['table_name']} ({r['table_cn_name']})")
        print(f"  分区: {r['partition_key']}")
        for c in r['columns']:
            print(f"  - {c}")

    print("\n=== get_metric('总资产') ===")
    for m in get_metric('总资产'):
        print(f"  {m['metric_name']}: {m['metric_formula']}")
