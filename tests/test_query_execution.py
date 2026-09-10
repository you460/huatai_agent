import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main


class _Cursor:
    description = [('pty_id',)]

    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchmany(self, size):
        self.fetch_size = size
        return self.rows


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.session = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set_session(self, **kwargs):
        self.session = kwargs

    def cursor(self):
        return self._cursor


class QueryExecutionTest(unittest.TestCase):
    def test_extract_sql_rejects_control_text_without_query(self):
        self.assertEqual(main.extract_sql('<｜｜DS'), '')

    @patch('main.AGENT_MAX_ROUNDS', 2)
    @patch('main.call_llm')
    def test_missing_sql_is_generation_failure_with_response_evidence(self, call_llm):
        message = SimpleNamespace(content='<｜｜DS', tool_calls=None)
        call_llm.return_value = SimpleNamespace(choices=[SimpleNamespace(message=message)])

        result = main.run_agent('客户数量', return_result=True)

        self.assertEqual(result.kind, 'agent_generation_error')
        self.assertEqual(result.details['stage'], 'model_response')
        self.assertIn('response_summary', result.details)

    def test_inclusive_age_consistency_guard_is_generic(self):
        for age in ('40', '60', '75'):
            with self.subTest(age=age):
                valid, error = main.check_question_sql_consistency(
                    f'{age}岁以上客户数量',
                    f'SELECT COUNT(*) FROM t WHERE cust_age > {age}',
                )
                self.assertFalse(valid)
                self.assertIn('>=', error)
                self.assertEqual(
                    main.check_question_sql_consistency(
                        f'{age}岁以上客户数量',
                        f'SELECT COUNT(*) FROM t WHERE cust_age >= {age}',
                    ),
                    (True, None),
                )

    def test_rejects_product_penetration_from_dimension_left_join(self):
        valid, error = main.check_question_sql_consistency(
            '各产品一级分类的客户渗透率',
            'SELECT p.up_prdt_type_name, COUNT(h.pty_id) FROM dim_product p '
            'LEFT JOIN dwd_cust_hold_d h ON h.prdt_id=p.prdt_id GROUP BY p.up_prdt_type_name',
        )
        self.assertFalse(valid)
        self.assertIn('实际持仓分类', error)
        self.assertEqual(main.check_question_sql_consistency(
            '各产品一级分类的客户渗透率',
            'SELECT p.up_prdt_type_name, COUNT(h.pty_id) FROM dwd_cust_hold_d h '
            'INNER JOIN dim_product p ON h.prdt_id=p.prdt_id GROUP BY p.up_prdt_type_name',
        ), (True, None))

    def test_rejects_average_holding_grouped_by_nullable_hold_customer(self):
        valid, error = main.check_question_sql_consistency(
            '女性客户与男性客户的平均持仓市值差值',
            'SELECT c.gender_cd, AVG(x) FROM ads_cust_info_d c '
            'LEFT JOIN dwd_cust_hold_d h ON c.pty_id=h.pty_id GROUP BY c.gender_cd,h.pty_id',
        )
        self.assertFalse(valid)
        self.assertIn('客户粒度', error)
        self.assertEqual(main.check_question_sql_consistency(
            '女性客户与男性客户的平均持仓市值差值',
            'WITH h AS (SELECT pty_id,SUM(mkt_val) v FROM dwd_cust_hold_d GROUP BY pty_id) '
            'SELECT AVG(COALESCE(h.v,0)) FROM ads_cust_info_d c LEFT JOIN h ON c.pty_id=h.pty_id',
        ), (True, None))

    def test_rejects_reversed_profit_detail_asset_columns(self):
        valid, error = main.check_question_sql_consistency(
            '计算客户一季度盈亏情况',
            'WITH b AS (SELECT 1 AS begin_aset), e AS (SELECT 2 AS end_aset) '
            'SELECT e.end_aset AS end_aset, b.begin_aset AS begin_aset FROM b,e',
        )
        self.assertFalse(valid)
        self.assertIn('期初资产', error)

    def test_rejects_branch_average_aggregated_only_by_org_id(self):
        valid, error = main.check_question_sql_consistency(
            '客户平均总资产最高的十个营业部',
            'WITH x AS (SELECT c.org_id, AVG(a.x) v FROM customer c JOIN asset a ON 1=1 '
            'GROUP BY c.org_id) SELECT b.up_org_name,b.org_name,x.v FROM x JOIN branch b ON 1=1',
        )
        self.assertFalse(valid)
        self.assertIn('最终展示', error)
    @patch('main.check_sql_safety', return_value=(True, None))
    @patch('main.execute_sql', return_value=(['cust_cnt'], [(15,)], None))
    @patch('main.call_llm')
    def test_agent_retries_wrong_inclusive_age_boundary(self, call_llm, execute_sql, _check):
        wrong = SimpleNamespace(
            content="SELECT COUNT(*) FROM t WHERE cust_age > 60", tool_calls=None
        )
        corrected = SimpleNamespace(
            content="SELECT COUNT(*) FROM t WHERE cust_age >= 60", tool_calls=None
        )
        call_llm.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=wrong)]),
            SimpleNamespace(choices=[SimpleNamespace(message=corrected)]),
        ]

        result = main.run_agent('60岁以上客户数量', return_result=True)

        self.assertEqual(result.rows, [(15,)])
        execute_sql.assert_called_once_with('SELECT COUNT(*) FROM t WHERE cust_age >= 60')

    @patch('main.check_sql_safety', return_value=(True, None))
    @patch('main.execute_sql', return_value=(['cust_cnt'], [(15,)], None))
    @patch('main.call_llm')
    def test_relevant_business_rule_is_attached_to_question(self, call_llm, _execute, _check):
        message = SimpleNamespace(
            content="SELECT COUNT(*) FROM ads_cust_info_d WHERE cust_age>=60",
            tool_calls=None,
        )
        call_llm.return_value = SimpleNamespace(choices=[SimpleNamespace(message=message)])

        main.run_agent('60岁以上客户数量', return_result=True)

        sent_messages = call_llm.call_args.args[0]
        self.assertIn('必须使用cust_age>=X', sent_messages[1]['content'])

    @patch('main.AGENT_MAX_ROUNDS', 3)
    @patch('main.check_sql_safety', return_value=(True, None))
    @patch('main.execute_sql', return_value=(['cust_cnt'], [(1,)], None))
    @patch('main.execute_tool_call', return_value=({'table': 'ok'}, 'cache-key'))
    @patch('main.call_llm')
    def test_agent_disables_tools_near_round_limit(self, call_llm, _tool, _execute, _check):
        tool_call = SimpleNamespace(id='call-1')
        tool_message = SimpleNamespace(content=None, tool_calls=[tool_call])
        sql_message = SimpleNamespace(content='SELECT COUNT(*) AS cust_cnt FROM ads_cust_info_d', tool_calls=None)
        call_llm.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=tool_message)]),
            SimpleNamespace(choices=[SimpleNamespace(message=sql_message)]),
        ]

        result = main.run_agent('各职业高净值客户数量', return_result=True)

        self.assertEqual(result.rows, [(1,)])
        self.assertTrue(call_llm.call_args_list[0].kwargs['allow_tools'])
        self.assertFalse(call_llm.call_args_list[1].kwargs['allow_tools'])

    @patch('main.AGENT_MAX_ROUNDS', 12)
    @patch('main.check_sql_safety', return_value=(True, None))
    @patch('main.execute_sql', return_value=(['total_aset'], [(100,)], None))
    @patch('main.execute_tool_call', return_value=([], 'get_metric:资产分布'))
    @patch('main.call_llm')
    def test_repeated_tool_call_forces_fresh_sql_synthesis(
        self, call_llm, _tool, _execute, _check
    ):
        tool_call = SimpleNamespace(id='call-1')
        tool_message = SimpleNamespace(content=None, tool_calls=[tool_call])
        sql_message = SimpleNamespace(
            content='SELECT SUM(total_aset) AS total_aset FROM t', tool_calls=None
        )
        call_llm.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=tool_message)]),
            SimpleNamespace(choices=[SimpleNamespace(message=tool_message)]),
            SimpleNamespace(choices=[SimpleNamespace(message=sql_message)]),
        ]

        result = main.run_agent('各年龄段资产分布', return_result=True)

        self.assertEqual(result.rows, [(100,)])
        final_call = call_llm.call_args_list[2]
        self.assertFalse(final_call.kwargs['allow_tools'])
        self.assertEqual(len(final_call.args[0]), 3)

    @patch('main.AGENT_MAX_ROUNDS', 3)
    @patch('main.execute_sql', return_value=(['total_aset'], [(100,)], None))
    @patch('main.check_sql_safety')
    @patch('main.call_llm')
    def test_forced_synthesis_keeps_latest_validation_error(
        self, call_llm, check_sql, _execute
    ):
        wrong = SimpleNamespace(content='SELECT * FROM wrong_table', tool_calls=None)
        corrected = SimpleNamespace(content='SELECT * FROM right_table', tool_calls=None)
        call_llm.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=wrong)]),
            SimpleNamespace(choices=[SimpleNamespace(message=corrected)]),
        ]
        check_sql.side_effect = [(False, '表名不存在: wrong_table'), (True, None)]

        result = main.run_agent('资产合计', return_result=True)

        self.assertEqual(result.rows, [(100,)])
        final_messages = call_llm.call_args_list[1].args[0]
        self.assertIn('表名不存在: wrong_table', final_messages[-1]['content'])

    @patch('main.check_sql_safety', return_value=(True, None))
    @patch('main.psycopg2.connect')
    def test_large_result_is_rejected_without_fetchall(self, connect, _check):
        cursor = _Cursor([(index,) for index in range(main.SQL_MAX_RESULT_ROWS + 1)])
        connection = _Connection(cursor)
        connect.return_value = connection

        columns, rows, error = main.execute_sql(
            "SELECT pty_id FROM ads_cust_info_d LIMIT 1001"
        )

        self.assertIsNone(columns)
        self.assertIsNone(rows)
        self.assertIn('最大返回行数', error)
        self.assertEqual(cursor.fetch_size, main.SQL_MAX_RESULT_ROWS + 1)
        self.assertEqual(connection.session, {'readonly': True, 'autocommit': True})

    @patch('main.check_sql_safety', return_value=(True, None))
    @patch('main.psycopg2.connect')
    def test_aggregate_result_is_returned_completely(self, connect, _check):
        cursor = _Cursor([(500,)])
        connect.return_value = _Connection(cursor)

        columns, rows, error = main.execute_sql(
            "SELECT COUNT(*) FROM ads_cust_info_d"
        )

        self.assertIsNone(error)
        self.assertEqual(columns, ['pty_id'])
        self.assertEqual(rows, [(500,)])

    @patch('main.check_sql_safety', return_value=(True, None))
    @patch('main.execute_sql', return_value=(['cust_cnt'], [(500,)], None))
    @patch('main.call_llm')
    def test_agent_executes_final_sql_once_and_returns_cached_result(
        self, call_llm, execute_sql, _check
    ):
        message = SimpleNamespace(content="SELECT COUNT(*) FROM ads_cust_info_d", tool_calls=None)
        call_llm.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=message)]
        )

        result = main.run_agent('客户总数', return_result=True)

        execute_sql.assert_called_once_with("SELECT COUNT(*) FROM ads_cust_info_d")
        self.assertEqual(result.columns, ['cust_cnt'])
        self.assertEqual(result.rows, [(500,)])

    @patch('main.check_sql_safety', return_value=(True, None))
    @patch('main.execute_sql', return_value=(['cust_cnt'], [(500,)], None))
    @patch('main.call_llm')
    def test_legacy_agent_interface_still_returns_sql(self, call_llm, _execute_sql, _check):
        message = SimpleNamespace(content='SELECT COUNT(*) FROM ads_cust_info_d', tool_calls=None)
        call_llm.return_value = SimpleNamespace(choices=[SimpleNamespace(message=message)])

        self.assertEqual(
            main.run_agent('客户总数'), 'SELECT COUNT(*) FROM ads_cust_info_d'
        )

    @patch('main.call_llm')
    def test_model_failure_keeps_sanitised_diagnostic_in_agent_failure(self, call_llm):
        call_llm.return_value = main.LLMCallFailure(
            '模型调用失败，已重试3次: HTTP 429: rate limited',
            {'stage': 'model_api', 'attempts': 3, 'error': 'HTTP 429: rate limited'},
        )

        result = main.run_agent('客户总数', return_result=True)

        self.assertIsInstance(result, main.AgentFailure)
        self.assertEqual(result.kind, 'agent_generation_error')
        self.assertIn('HTTP 429', result.message)
        self.assertEqual(result.details['stage'], 'model_api')

    @patch('main.SQL_MAX_EXEC_ERRORS', 1)
    @patch('main.check_sql_safety', return_value=(True, None))
    @patch('main.execute_sql', return_value=(None, None, 'statement timeout'))
    @patch('main.call_llm')
    def test_execution_failure_preserves_last_sql(self, call_llm, _execute, _check):
        sql = 'SELECT COUNT(*) FROM ads_cust_info_d'
        message = SimpleNamespace(content=sql, tool_calls=None)
        call_llm.return_value = SimpleNamespace(choices=[SimpleNamespace(message=message)])

        result = main.run_agent('客户数', return_result=True)

        self.assertEqual(result.kind, 'agent_execution_error')
        self.assertEqual(result.details['sql'], sql)
        self.assertIn('timeout', result.details['error'])

    @patch('main.AGENT_MAX_ROUNDS', 1)
    @patch('main.check_sql_safety', return_value=(False, '只允许 SELECT'))
    @patch('main.call_llm')
    def test_security_rejection_is_not_reported_as_generation_failure(
        self, call_llm, _check
    ):
        message = SimpleNamespace(content='DELETE FROM ads_cust_info_d', tool_calls=None)
        call_llm.return_value = SimpleNamespace(choices=[SimpleNamespace(message=message)])

        result = main.run_agent('删除客户', return_result=True)

        self.assertEqual(result.kind, 'agent_validation_error')
        self.assertEqual(result.details['stage'], 'security_validation')


if __name__ == '__main__':
    unittest.main()
