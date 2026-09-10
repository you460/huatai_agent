import importlib.util
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path


def load_evaluate_module():
    previous_main = sys.modules.get('main')
    main_stub = types.ModuleType('main')
    main_stub.run_agent = None
    main_stub.execute_sql = None
    sys.modules['main'] = main_stub

    try:
        path = Path(__file__).parents[1] / 'evaluation' / 'evaluate.py'
        spec = importlib.util.spec_from_file_location('evaluate_for_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_main is None:
            sys.modules.pop('main', None)
        else:
            sys.modules['main'] = previous_main


evaluate = load_evaluate_module()


class EvaluateCompareTest(unittest.TestCase):
    def test_question_scoring_flag_defaults_to_true(self):
        self.assertTrue(evaluate.is_question_scored({'id': 1}))
        self.assertFalse(evaluate.is_question_scored({'valid_for_scoring': False}))

    def test_parses_optional_question_ids(self):
        self.assertEqual(evaluate.parse_question_ids(''), set())
        self.assertEqual(evaluate.parse_question_ids('37, 102,104'), {37, 102, 104})

    def test_compact_suite_is_fixed_balanced_and_contains_official_examples(self):
        questions = [
            {'id': item, 'difficulty': difficulty}
            for difficulty, start in (('简单', 1), ('中等', 51), ('较难', 101))
            for item in range(start, start + 50)
        ]
        selected, suite = evaluate.select_suite(questions, 'compact90')
        self.assertEqual(len(selected), 90)
        self.assertEqual(
            {difficulty: sum(q['difficulty'] == difficulty for q in selected)
             for difficulty in ('简单', '中等', '较难')},
            {'简单': 30, '中等': 30, '较难': 30},
        )
        self.assertTrue({51, 52, 53, 101, 102, 103, 104}.issubset(
            {question['id'] for question in selected}
        ))
        self.assertIn('不参考模型得分', suite['description'])

    def test_source_metrics_are_reported_separately(self):
        metrics = evaluate._group_metrics([
            {'source': 'official', 'value_match': True, 'schema_match': True, 'overall_success': True},
            {'source': 'self', 'value_match': True, 'schema_match': False, 'overall_success': False},
        ], 'source')
        self.assertEqual(metrics['official']['overall_success'], 1)
        self.assertEqual(metrics['self']['schema_match'], 0)

    def test_prefers_reviewed_question_value(self):
        question = {'question': '官方原题', 'reviewed_question': '审核题干'}
        self.assertEqual(evaluate.reviewed_value(question, 'question'), '审核题干')
        self.assertEqual(
            evaluate.reviewed_value({'question': '官方原题'}, 'question'), '官方原题'
        )

    def test_allows_unordered_normal_groups(self):
        self.assertTrue(evaluate.compare_results(
            ['分公司名称', '客户数量'], [('北京', 100), ('上海', 200)],
            ['分公司', '客户数'], [('上海', 200), ('北京', 100)], '各分公司客户数'
        ))

    def test_rejects_different_field_semantics_even_when_values_match(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 77, 'question': '各分公司客户数量排名'},
            ['营业部', '客户数量'], [('北京营业部', 100)],
            ['分公司', '客户数'], [('北京营业部', 100)],
        )
        self.assertFalse(correct)
        self.assertEqual(evidence['difference_type'], '字段语义错误')
        self.assertTrue(evidence['result_check']['passed'])

    def test_allows_reasonable_chinese_metric_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 25, 'question': '持仓总市值'},
            ['持仓总市值'], [(100,)], ['tot_mkt_val'], [(100,)],
            'SELECT SUM(mkt_val) AS 持仓总市值 FROM hold',
            'SELECT SUM(mkt_val) AS tot_mkt_val FROM hold',
        )
        self.assertTrue(correct, msg=evidence)

    def test_allows_reasonable_english_metric_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 26, 'question': '总买入金额'},
            ['total_buy_amt'], [(100,)], ['tot_buy_amt'], [(100,)],
            'SELECT SUM(buy_amt) AS total_buy_amt FROM trade',
            'SELECT SUM(buy_amt) AS tot_buy_amt FROM trade',
        )
        self.assertTrue(correct, msg=evidence)

    def test_allows_education_level_chinese_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 95, 'question': '统计各学历层级的男性客户数量'},
            ['学历层级', '男性客户数量'], [('大专', 115)],
            ['edu_name', 'cust_cnt'], [('大专', 115)],
            'SELECT describe AS 学历层级, COUNT(*) AS 男性客户数量 FROM t GROUP BY describe',
            'SELECT describe AS edu_name, COUNT(*) AS cust_cnt FROM t GROUP BY describe',
        )
        self.assertTrue(correct, msg=evidence)

    def test_allows_education_level_english_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 95, 'question': '统计各学历层级的男性客户数量'},
            ['edu_level', 'male_cust_cnt'], [('大专', 115)],
            ['edu_name', 'cust_cnt'], [('大专', 115)],
        )
        self.assertTrue(correct, msg=evidence)

    def test_allows_commission_rate_english_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 114, 'question': '各省份客户的整体交易佣金率'},
            ['prov_name', 'commission_rate'], [('江苏省', Decimal('0.001'))],
            ['prov_name', 'avg_rake_rate'], [('江苏省', Decimal('0.001'))],
            'SELECT prov_name, rake / amount AS commission_rate FROM t',
            'SELECT prov_name, rake / amount AS avg_rake_rate FROM t',
        )
        self.assertTrue(correct, msg=evidence)

    def test_account_source_code_and_chinese_label_are_equivalent(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 72, 'question': '普通账户和信用账户的总交易金额分别是多少'},
            ['account_type', 'total_tran_amt'], [('普通账户', 100), ('信用账户', 80)],
            ['sys_source', 'tot_tran_amt'], [('nm', 100), ('fc', 80)],
            "SELECT CASE sys_source WHEN 'nm' THEN '普通账户' WHEN 'fc' THEN '信用账户' END AS account_type, SUM(amt) AS total_tran_amt FROM t GROUP BY sys_source",
            'SELECT sys_source, SUM(amt) AS tot_tran_amt FROM t GROUP BY sys_source',
        )
        self.assertTrue(correct, msg=evidence)

    def test_account_source_mapping_is_strict(self):
        self.assertFalse(evaluate.values_equal('普通账户', 'fc'))
        self.assertFalse(evaluate.values_equal('营业部', '分公司'))

    def test_allows_account_source_display_name_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 1001, 'question': '按账户来源汇总成交额'},
            ['sys_source_name', 'total_tran_amt'], [('普通账户', 100)],
            ['sys_source', 'tot_tran_amt'], [('nm', 100)],
        )
        self.assertTrue(correct, msg=evidence)

    def test_distinguishes_begin_and_end_asset_columns(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 1002, 'question': '客户盈亏情况'},
            ['end_aset', 'begin_aset'], [(200, 100)],
            ['bgn_aset', 'end_aset'], [(100, 200)],
        )
        self.assertFalse(correct)
        self.assertFalse(evidence['field_check']['passed'])

    def test_allows_profit_loss_business_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 101, 'question': '客户盈亏情况'},
            ['profit_loss'], [(100,)], ['aset_pft'], [(100,)],
            'SELECT end_aset - begin_aset + outflow - inflow AS profit_loss FROM t',
            'SELECT end_aset - begin_aset + aset_out - aset_in AS aset_pft FROM t',
        )
        self.assertTrue(correct, msg=evidence)

    def test_allows_common_english_profit_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 999, 'question': '给出客户一季度盈亏情况明细'},
            ['pty_id', 'begin_aset', 'end_aset', 'inflow', 'outflow', 'profit'],
            [('C1', 100, 120, 10, 5, 15)],
            ['pty_id', 'bgn_aset', 'end_aset', 'aset_in', 'aset_out', 'aset_pft'],
            [('C1', 100, 120, 10, 5, 15)],
            ('SELECT pty_id, begin_aset, end_aset, inflow, outflow, '
             'end_aset - begin_aset + outflow - inflow AS profit FROM result'),
            ('SELECT pty_id, bgn_aset, end_aset, aset_in, aset_out, '
             'end_aset - bgn_aset + aset_out - aset_in AS aset_pft FROM result'),
        )
        self.assertTrue(correct, msg=evidence)
        self.assertTrue(evidence['result_check']['passed'])
        self.assertTrue(evidence['field_check']['passed'])

    def test_inferrs_unaliased_aggregate_semantic_from_sql_expression(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 29, 'question': '客户平均年龄'},
            ['round'], [(45.5,)], ['avg_age'], [(45.5,)],
            'SELECT ROUND(AVG(cust_age), 2) FROM customer',
            'SELECT ROUND(AVG(cust_age), 2) AS avg_age FROM customer',
        )
        self.assertTrue(correct, msg=evidence)

    def test_unaliased_count_uses_sql_subject(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 20, 'question': 'A股产品数量'},
            ['count'], [(10,)], ['prdt_cnt'], [(10,)],
            'SELECT COUNT(*) FROM dim_product WHERE prdt_type_name = \'A股\'',
            'SELECT COUNT(*) AS prdt_cnt FROM dim_product WHERE prdt_type_name = \'A股\'',
        )
        self.assertTrue(correct, msg=evidence)

    def test_count_star_prefers_expected_customer_contract_over_joined_product_table(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 84, 'question': '交易金额大于50万元的客户数量'},
            ['count'], [(3,)], ['cust_cnt'], [(3,)],
            'SELECT COUNT(*) FROM (SELECT t.pty_id FROM dwd_cust_tran_d t '
            'JOIN dim_product p ON t.prdt_id=p.prdt_id GROUP BY t.pty_id) x',
            'SELECT COUNT(*) AS cust_cnt FROM (SELECT pty_id FROM dwd_cust_tran_d GROUP BY pty_id) x',
        )
        self.assertTrue(correct, msg=evidence)

    def test_explicit_product_count_does_not_pass_customer_count_contract(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 84, 'question': '客户数量'},
            ['count'], [(3,)], ['cust_cnt'], [(3,)],
            'SELECT COUNT(DISTINCT prdt_id) FROM dwd_cust_tran_d',
            'SELECT COUNT(DISTINCT pty_id) AS cust_cnt FROM dwd_cust_tran_d',
        )
        self.assertFalse(correct)
        self.assertFalse(evidence['field_check']['passed'])
        self.assertTrue(evidence['result_check']['passed'])

    def test_penetration_rate_contract_uses_numeric_tolerance(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 143, 'question': '各产品一级分类的客户渗透率'},
            ['up_prdt_type_name', 'penetration_rate'], [('股票', Decimal('0.8300'))],
            ['up_prdt_type_name', 'penetration'], [('股票', Decimal('0.83000000000000000000'))],
            'SELECT up_prdt_type_name, ROUND(cnt * 1.0 / total, 4) AS penetration_rate FROM t',
            'SELECT up_prdt_type_name, cnt * 1.0 / total AS penetration FROM t',
        )
        self.assertTrue(correct, msg=evidence)

    def test_detail_reports_value_schema_and_overall_separately(self):
        evidence = {
            'field_check': {'passed': False, 'evidence': {'summary': '字段错误'}},
            'result_check': {'passed': True, 'evidence': None},
        }
        detail = evaluate._detail(
            {'id': 84, 'difficulty': '中等', 'question': '客户数量'},
            'SELECT COUNT(*) FROM t', 'SELECT COUNT(*) AS cust_cnt FROM t',
            0, '字段语义错误', '字段错误', ['count'], [(3,)], ['cust_cnt'], [(3,)],
            comparison_evidence=evidence,
        )
        self.assertTrue(detail['value_match'])
        self.assertFalse(detail['schema_match'])
        self.assertFalse(detail['overall_success'])

    def test_never_maps_branch_office_to_branch_company(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 77, 'question': '各分公司客户数量排名'},
            ['营业部', '客户数量'], [('北京营业部', 100)],
            ['分公司', '客户数'], [('北京营业部', 100)],
            'SELECT org_name AS 营业部, COUNT(*) AS 客户数量 FROM t GROUP BY org_name',
            'SELECT up_org_name AS 分公司, COUNT(*) AS 客户数 FROM t GROUP BY up_org_name',
        )
        self.assertFalse(correct)
        self.assertEqual(evidence['difference_type'], '字段语义错误')
        self.assertTrue(evidence['result_check']['passed'])

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

    def test_ranking_allows_reordering_within_ties(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 77, 'question': '各分公司客户数量排名'},
            ['分公司名称', '客户数量'], [('上海', 10), ('北京', 10), ('南京', 8)],
            ['分公司', '客户数'], [('北京', 10), ('上海', 10), ('南京', 8)],
        )
        self.assertTrue(correct, msg=evidence)

    def test_ranking_numeric_keys_use_rounding_tolerance(self):
        correct, evidence = evaluate._compare_ranked_rows(
            [('甲', '762977.89'), ('乙', '500375.00')],
            [('甲', '762977.885000000000'), ('乙', '500375.000000000000')],
            [1], 'free',
        )
        self.assertTrue(correct, msg=evidence)

    def test_chinese_and_mathematical_interval_labels_are_equivalent(self):
        pairs = [
            ('小于30', '<30'),
            ('大于等于30，小于50', '[30,50)'),
            ('大于等于50，小于60', '[50,60)'),
            ('大于等于60', '[60,)'),
        ]
        for chinese, mathematical in pairs:
            with self.subTest(chinese=chinese):
                self.assertTrue(evaluate.values_equal(chinese, mathematical))

    def test_interval_normalisation_preserves_open_closed_boundaries(self):
        self.assertFalse(evaluate.values_equal('大于60', '[60,)'))
        self.assertFalse(evaluate.values_equal('大于等于60', '(60,)'))

    def test_discrete_integer_interval_labels_are_equivalent(self):
        self.assertTrue(evaluate.values_equal('30-49', '[30,50)'))
        self.assertTrue(evaluate.values_equal('50-59', '[50,60)'))
        self.assertTrue(evaluate.values_equal('60及以上', '[60,)'))

    def test_allows_product_category_chinese_aliases(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 82, 'question': '各产品二级分类的交易金额排名'},
            ['二级分类', '交易金额'], [('A股', 100)],
            ['prdt_type_name', 'tran_amt'], [('A股', 100)],
        )
        self.assertTrue(correct, msg=evidence)

    def test_allows_category_word_as_same_product_level_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 999, 'question': '按产品一级类别统计客户覆盖率'},
            ['产品一级类别', '渗透率'], [('股票', 0.25)],
            ['up_prdt_type_name', 'penetration_rate'], [('股票', 0.25)],
            'SELECT up_prdt_type_name AS 产品一级类别, 0.25 AS 渗透率 FROM t',
            'SELECT up_prdt_type_name, 0.25 AS penetration_rate FROM t',
        )
        self.assertTrue(correct, msg=evidence)

        wrong, wrong_evidence = evaluate.compare_with_evidence(
            {'id': 999, 'question': '按产品一级类别统计客户覆盖率'},
            ['产品二级类别', '渗透率'], [('股票', 0.25)],
            ['up_prdt_type_name', 'penetration_rate'], [('股票', 0.25)],
            'SELECT prdt_type_name AS 产品二级类别, 0.25 AS 渗透率 FROM t',
            'SELECT up_prdt_type_name, 0.25 AS penetration_rate FROM t',
        )
        self.assertFalse(wrong)
        self.assertFalse(wrong_evidence['field_check']['passed'])

    def test_allows_trade_rake_rate_alias(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 114, 'question': '各省份整体交易佣金率'},
            ['prov_name', 'trade_rake_rate'], [('江苏省', Decimal('0.001'))],
            ['prov_name', 'avg_rake_rate'], [('江苏省', Decimal('0.001'))],
        )
        self.assertTrue(correct, msg=evidence)

    def test_ranking_rejects_wrong_primary_sort_order(self):
        correct, evidence = evaluate.compare_with_evidence(
            {'id': 77, 'question': '各分公司客户数量排名'},
            ['分公司名称', '客户数量'], [('南京', 8), ('北京', 10)],
            ['分公司', '客户数'], [('北京', 10), ('南京', 8)],
        )
        self.assertFalse(correct)
        self.assertEqual(evidence['difference_type'], '排序不一致')

    def test_fixed_tie_order_requires_explicit_secondary_order(self):
        correct, evidence = evaluate._compare_ranked_rows(
            [('北京', 10), ('上海', 10)], [('上海', 10), ('北京', 10)], [1], 'fixed',
            'SELECT city, amount FROM t ORDER BY amount DESC',
            'SELECT city, amount FROM t ORDER BY amount DESC',
        )
        self.assertFalse(correct)
        self.assertIn('二级 ORDER BY', evidence['summary'])

    def test_result_snapshot_records_evidence_and_hash(self):
        snapshot = evaluate._result_snapshot(['客户数'], [(1,), (2,)])
        self.assertEqual(snapshot['columns'], ['客户数'])
        self.assertEqual(snapshot['row_count'], 2)
        self.assertEqual(snapshot['sample_rows'], [[1], [2]])
        self.assertEqual(len(snapshot['normalised_result_hash']), 64)

    def test_detail_preserves_agent_failure_evidence(self):
        detail = evaluate._detail(
            {'id': 1, 'difficulty': '简单', 'question': '客户数'}, None,
            'SELECT COUNT(*) AS cust_cnt FROM t', 1.0, 'Agent生成失败',
            '模型调用失败，已重试3次: HTTP 429',
            standard_columns=['cust_cnt'], standard_rows=[(1,)],
            failure_evidence={'stage': 'model_api', 'attempts': 3, 'error': 'HTTP 429'},
        )
        self.assertEqual(detail['failure_evidence']['stage'], 'model_api')
        self.assertIn('HTTP 429', detail['difference_summary'])

    def test_run_metadata_has_reproducibility_fields(self):
        metadata = evaluate._run_metadata(
            Path(__file__).parents[1] / 'evaluation' / 'test_questions.json'
        )
        for field in (
            'evaluation_rules_version', 'question_bank_sha256', 'data_snapshot_id',
            'model', 'prompt_version', 'code_version', 'code_snapshot_sha256',
            'run_started_at',
        ):
            self.assertIn(field, metadata)
        self.assertEqual(len(metadata['code_snapshot_sha256']), 64)


if __name__ == '__main__':
    unittest.main()
