import sqlglot
from metadata_tools import METADATA


# 从元数据中提取所有合法的表名和字段名
VALID_TABLES = set()
VALID_COLUMNS = {}  # 表名 -> 字段名集合

for table in METADATA['tables']:
    table_name = table['table_name']
    VALID_TABLES.add(table_name)
    VALID_COLUMNS[table_name] = set()
    for col in table.get('columns', []):
        VALID_COLUMNS[table_name].add(col['column_name'])


def check_sql_safety(sql):
    """检查 SQL 是否安全，返回是否安全和错误信息。"""
    # 检查1：只允许SELECT
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith('SELECT') and not sql_upper.startswith('WITH'):
        return False, "只允许SELECT查询语句，禁止其他操作"
    
    # 检查2：语法检查
    try:
        parsed = sqlglot.parse_one(sql, read='postgres')
    except Exception as e:
        return False, f"SQL语法错误: {str(e)[:100]}"
    
    # 检查3：表名校验
    if parsed:
        try:
            # 收集 CTE 别名，这些不是真实表
            cte_aliases = set()
            for cte in parsed.find_all(sqlglot.exp.CTE):
                if cte.alias:
                    cte_aliases.add(cte.alias)
            
            tables_in_sql = set()
            for table in parsed.find_all(sqlglot.exp.Table):
                table_name = table.name
                # 跳过CTE别名和子查询别名
                if table_name in cte_aliases:
                    continue
                tables_in_sql.add(table_name)
                if table_name not in VALID_TABLES:
                    return False, f"表名不存在: {table_name}，合法表名: {', '.join(sorted(VALID_TABLES))}"
        except Exception as e:
            pass  # 表名校验出错不阻断
    
    # 检查4：字段名校验
    if parsed:
        try:
            for column in parsed.find_all(sqlglot.exp.Column):
                col_name = column.name
                table_alias = column.table
                
                # 如果字段指定了表别名，需要找到对应的真实表名
                if table_alias:
                    # 从SQL中找别名对应的真实表名
                    real_table = find_table_by_alias(parsed, table_alias)
                    if real_table and real_table in VALID_COLUMNS:
                        if col_name not in VALID_COLUMNS[real_table]:
                            return False, f"字段名不存在: {real_table}.{col_name}"
        except Exception as e:
            # 字段名校验出错不阻断，只记录
            pass
    
    return True, None


def find_table_by_alias(parsed, alias):
    """按别名找真实表名。"""
    for table in parsed.find_all(sqlglot.exp.Table):
        if table.alias == alias:
            return table.name
    return None


# 测试代码
if __name__ == '__main__':
    print("=== 安全围栏测试 ===")
    print()
    
    # 测试1：正常SELECT
    sql1 = "SELECT COUNT(*) FROM ads_cust_info_d WHERE data_dt = '20260531'"
    safe, err = check_sql_safety(sql1)
    print(f"测试1（正常SELECT）: {'✅ 通过' if safe else f'❌ {err}'}")
    
    # 测试2：INSERT（应该被拦截）
    sql2 = "INSERT INTO ads_cust_info_d VALUES ('test')"
    safe, err = check_sql_safety(sql2)
    print(f"测试2（INSERT）: {'✅ 通过' if safe else f'❌ {err}'}")
    
    # 测试3：DELETE（应该被拦截）
    sql3 = "DELETE FROM ads_cust_info_d WHERE 1=1"
    safe, err = check_sql_safety(sql3)
    print(f"测试3（DELETE）: {'✅ 通过' if safe else f'❌ {err}'}")
    
    # 测试4：DROP（应该被拦截）
    sql4 = "DROP TABLE ads_cust_info_d"
    safe, err = check_sql_safety(sql4)
    print(f"测试4（DROP）: {'✅ 通过' if safe else f'❌ {err}'}")
    
    # 测试5：不存在的表（应该被拦截）
    sql5 = "SELECT * FROM non_exist_table"
    safe, err = check_sql_safety(sql5)
    print(f"测试5（不存在的表）: {'✅ 通过' if safe else f'❌ {err}'}")
    
    # 测试6：语法错误（应该被拦截）
    sql6 = "SELECT COUNT(*) FROM ads_cust_info_d WHERE"
    safe, err = check_sql_safety(sql6)
    print(f"测试6（语法错误）: {'✅ 通过' if safe else f'❌ {err}'}")
    
    # 测试7：带别名的正常查询
    sql7 = "SELECT cust.pty_id, cust.name FROM ads_cust_info_d cust WHERE cust.data_dt = '20260531'"
    safe, err = check_sql_safety(sql7)
    print(f"测试7（带别名正常查询）: {'✅ 通过' if safe else f'❌ {err}'}")
    
    # 测试8：多表关联
    sql8 = """
    SELECT cust.name, aset.nm_tot_aset 
    FROM dws_cust_aset_d aset 
    JOIN ads_cust_info_d cust ON aset.pty_id = cust.pty_id 
    WHERE aset.data_dt = '20260331' AND cust.data_dt = '20260531'
    """
    safe, err = check_sql_safety(sql8)
    print(f"测试8（多表关联）: {'✅ 通过' if safe else f'❌ {err}'}")
