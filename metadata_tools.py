import json
import os

# 读取元数据JSON
METADATA_PATH = os.path.join(os.path.dirname(__file__), 'metadata', 'metadata.json')
with open(METADATA_PATH, 'r', encoding='utf-8') as f:
    METADATA = json.load(f)

TABLES = METADATA['tables']

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
