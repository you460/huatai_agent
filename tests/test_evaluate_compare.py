import importlib.util
import sys
import types
import unittest
from pathlib import Path


def load_evaluate_module():
    main_stub = types.ModuleType('main')
    main_stub.run_agent = None
    main_stub.execute_sql = None
    sys.modules['main'] = main_stub

    path = Path(__file__).parents[1] / 'evaluation' / 'evaluate.py'
    spec = importlib.util.spec_from_file_location('evaluate_for_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evaluate = load_evaluate_module()


class EvaluateCompareTest(unittest.TestCase):
    def test_question_scoring_flag_defaults_to_true(self):
        self.assertTrue(evaluate.is_question_scored({'id': 1}))
        self.assertFalse(evaluate.is_question_scored({'valid_for_scoring': False}))

    def test_parses_optional_question_ids(self):
        self.assertEqual(evaluate.parse_question_ids(''), set())
        self.assertEqual(evaluate.parse_question_ids('37, 102,104'), {37, 102, 104})

    def test_prefers_reviewed_question_value(self):
        question = {'question': '官方原题', 'reviewed_question': '审核题干'}
        self.assertEqual(evaluate.reviewed_value(question, 'question'), '审核题干')
        self.assertEqual(
            evaluate.reviewed_value({'question': '官方原题'}, 'question'), '官方原题'
        )

    def test_allows_unordered_normal_groups(self):
        self.assertTrue(evaluate.compare_results(
            ['营业部', '交易额'], [('北京', 100), ('上海', 200)],
            ['分支', '金额'], [('上海', 200), ('北京', 100)], '各营业部交易额'
        ))

    def test_rejects_different_group_dimension(self):
        self.assertFalse(evaluate.compare_results(
            ['营业部', '交易额'], [('北京', 100)],
            ['营业部', '交易额'], [('上海', 100)], '各营业部交易额'
        ))

    def test_rejects_different_column_count(self):
        self.assertFalse(evaluate.compare_results(
            ['交易额'], [(100,)], ['营业部', '交易额'], [('北京', 100)], '交易额'
        ))

    def test_rejects_percent_scale_difference(self):
        self.assertFalse(evaluate.compare_results(
            ['收益率'], [(0.1,)], ['收益率'], [(10,)], '收益率'
        ))

    def test_rejects_duplicate_row_mismatch(self):
        self.assertFalse(evaluate.compare_results(
            ['营业部', '交易额'], [('北京', 100), ('北京', 100), ('上海', 100)],
            ['营业部', '交易额'], [('北京', 100), ('上海', 100), ('上海', 100)], '各营业部交易额'
        ))

    def test_ranking_requires_same_order(self):
        self.assertFalse(evaluate.compare_results(
            ['营业部', '交易额'], [('北京', 200), ('上海', 100)],
            ['营业部', '交易额'], [('上海', 100), ('北京', 200)], '交易额排名前2的营业部'
        ))


if __name__ == '__main__':
    unittest.main()
