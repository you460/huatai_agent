import unittest
from unittest.mock import patch

import app
from main import AgentFailure, AgentResult


class AppSessionTest(unittest.TestCase):
    @patch('app.run_agent')
    def test_reuses_agent_result_without_a_second_sql_execution(self, run_agent):
        run_agent.return_value = AgentResult(
            sql="SELECT COUNT(*) AS cust_cnt FROM ads_cust_info_d",
            columns=['cust_cnt'],
            rows=[(500,)],
        )

        sql, result, _, history = app.answer('客户有多少位', [])

        run_agent.assert_called_once_with('客户有多少位', return_result=True)
        self.assertEqual(sql, run_agent.return_value.sql)
        self.assertEqual(result.iloc[0, 0], 500)
        self.assertEqual(len(history), 1)

    @patch('app.run_agent')
    def test_history_is_isolated_by_session_state(self, run_agent):
        run_agent.side_effect = [
            AgentResult('SELECT 1', ['value'], [(1,)]),
            AgentResult('SELECT 2', ['value'], [(2,)]),
        ]

        _, _, history_a_text, history_a = app.answer('会话A的问题', [])
        _, _, history_b_text, history_b = app.answer('会话B的问题', [])

        self.assertEqual([item['question'] for item in history_a], ['会话A的问题'])
        self.assertEqual([item['question'] for item in history_b], ['会话B的问题'])
        self.assertIn('会话A的问题', history_a_text)
        self.assertNotIn('会话B的问题', history_a_text)
        self.assertIn('会话B的问题', history_b_text)
        self.assertNotIn('会话A的问题', history_b_text)

    @patch('app.run_agent')
    def test_agent_failure_is_shown_without_changing_history(self, run_agent):
        run_agent.return_value = AgentFailure(
            'agent_generation_error', '模型服务暂时不可用', {'stage': 'model_api'}
        )

        sql_text, result, history_text, history = app.answer('客户有多少位', [])

        self.assertEqual(sql_text, '生成SQL失败：模型服务暂时不可用')
        self.assertTrue(result.empty)
        self.assertEqual(history_text, '暂无查询记录')
        self.assertEqual(history, [])


if __name__ == '__main__':
    unittest.main()
