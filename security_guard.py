import sqlglot
from sqlglot.optimizer.scope import traverse_scope
from metadata_tools import METADATA


# 从元数据中提取所有合法的表名和字段名
VALID_TABLES = set()
VALID_COLUMNS = {}  # 表名 -> 字段名集合

# 只允许返回查询结果的顶层语句。WITH ... SELECT 在 sqlglot 中的顶层节点仍是 SELECT。
READ_ONLY_QUERY_TYPES = {'SELECT', 'UNION', 'INTERSECT', 'EXCEPT'}
FORBIDDEN_NODE_TYPES = {
    'ALTER', 'COMMAND', 'COMMIT', 'COPY', 'CREATE', 'DELETE', 'DROP',
    'GRANT', 'INSERT', 'LOCK', 'MERGE', 'REVOKE', 'ROLLBACK',
    'TRANSACTION', 'TRUNCATE', 'UPDATE',
}

# 即使是 SELECT，以下函数也可能读取服务端文件、泄露会话信息或故意耗尽连接资源。
FORBIDDEN_FUNCTIONS = {
    'current_user', 'current_role', 'current_setting', 'current_database',
    'pg_backend_pid', 'pg_cancel_backend', 'pg_terminate_backend', 'pg_sleep',
    'pg_read_file', 'pg_read_binary_file', 'pg_ls_dir', 'pg_ls_logdir',
    'pg_stat_file', 'dblink', 'lo_export', 'lo_import', 'set_config',
}

for table in METADATA['tables']:
    table_name = table['table_name']
    VALID_TABLES.add(table_name)
    VALID_COLUMNS[table_name] = set()
    for col in table.get('columns', []):
        VALID_COLUMNS[table_name].add(col['column_name'])


def check_sql_safety(sql):
    """检查 SQL 是否安全，返回是否安全和错误信息。"""
    if not isinstance(sql, str) or not sql.strip():
        return False, "SQL不能为空"

    # 检查1：解析完整 SQL，并且只允许一条语句
    try:
        statements = [item for item in sqlglot.parse(sql, read='postgres') if item]
    except Exception as e:
        return False, f"SQL语法错误: {str(e)[:100]}"

    if len(statements) != 1:
        return False, "一次只允许执行一条SELECT查询语句"

    parsed = statements[0]
    if parsed.__class__.__name__.upper() not in READ_ONLY_QUERY_TYPES:
        return False, "只允许SELECT查询语句，禁止其他操作"

    # 检查2：即使顶层是 SELECT，也禁止数据修改 CTE 等写操作节点
    node_types = {node.__class__.__name__.upper() for node in parsed.walk()}
    forbidden_types = sorted(node_types & FORBIDDEN_NODE_TYPES)
    if forbidden_types:
        return False, f"检测到禁止的SQL操作: {', '.join(forbidden_types)}"

    # 检查3：拦截有副作用、可读取服务端信息或可阻塞连接的函数。
    try:
        for func in parsed.find_all(sqlglot.exp.Func):
            name = (getattr(func, 'name', '') or func.sql_name()).lower()
            if name in FORBIDDEN_FUNCTIONS:
                return False, f"禁止调用危险函数: {name}"
    except Exception as e:
        return False, f"函数安全校验失败: {str(e)[:100]}"

    # 检查4：表名校验。校验过程异常时必须拒绝，避免安全检查失效后放行。
    try:
        cte_aliases = {
            cte.alias
            for cte in parsed.find_all(sqlglot.exp.CTE)
            if cte.alias
        }

        for table in parsed.find_all(sqlglot.exp.Table):
            table_name = table.name
            if table_name in cte_aliases:
                continue
            if table_name not in VALID_TABLES:
                return False, f"表名不存在: {table_name}，合法表名: {', '.join(sorted(VALID_TABLES))}"
    except Exception as e:
        return False, f"表名安全校验失败: {str(e)[:100]}"

    # 检查5：按查询作用域校验带别名的字段；未限定字段仍由数据库负责判定。
    try:
        for scope in traverse_scope(parsed):
            for column in scope.columns:
                table_alias = column.table
                source = scope.sources.get(table_alias) if table_alias else None
                if isinstance(source, sqlglot.exp.Table):
                    real_table = source.name
                    if real_table in VALID_COLUMNS and column.name not in VALID_COLUMNS[real_table]:
                        return False, f"字段名不存在: {real_table}.{column.name}"
    except Exception as e:
        return False, f"字段名安全校验失败: {str(e)[:100]}"

    # 检查6：明细查询必须显式限制输出行数。聚合查询的计算仍由数据库完整执行，
    # 此处不注入 LIMIT，避免改变 COUNT/SUM/AVG 等指标的计算口径。
    try:
        has_limit = bool(parsed.args.get('limit'))
        has_group = bool(parsed.args.get('group'))
        has_aggregate = any(
            isinstance(node, sqlglot.exp.AggFunc)
            for node in parsed.find_all(sqlglot.exp.AggFunc)
        )
        if not has_limit and not has_group and not has_aggregate:
            return False, "明细查询必须包含 LIMIT，避免一次返回过多数据"
    except Exception as e:
        return False, f"结果行数安全校验失败: {str(e)[:100]}"
    
    return True, None

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
