import unittest

from metadata_tools import match_business_rules


class BusinessMetadataTest(unittest.TestCase):
    def assertRuleMatchesAll(self, rule_name, questions):
        for question in questions:
            with self.subTest(rule=rule_name, question=question):
                self.assertIn(rule_name, match_business_rules(question))

    def test_product_name_grouping_synonyms(self):
        self.assertRuleMatchesAll('product_name_grouping', [
            '统计每个产品的持仓市值', '按产品名称汇总成交额', '各产品交易笔数排名',
        ])

    def test_branch_grouping_synonyms(self):
        self.assertRuleMatchesAll('branch_grouping', [
            '各营业部买入金额', '每个营业部客户数', '营业部交易额排名',
        ])

    def test_stock_category_synonyms(self):
        self.assertRuleMatchesAll('stock_category', [
            '股票交易金额超过十万的客户', '统计股票持仓客户数量',
        ])

    def test_no_positive_asset_synonyms(self):
        self.assertRuleMatchesAll('no_positive_asset', [
            '季末没有正资产的客户', '期末无正资产的人数', '不存在正资产的客户',
        ])

    def test_ratio_projection_synonyms(self):
        self.assertRuleMatchesAll('ratio_projection', [
            '各分公司钻石卡客户占比', '计算客户比率', '产品渗透率排名',
        ])

    def test_average_asset_population_synonyms(self):
        self.assertRuleMatchesAll('average_asset_population', [
            '南京分公司客户的平均总资产', '各营业部总资产平均值', '分公司人均总资产',
        ])

    def test_snapshot_date_join_rule_synonyms(self):
        self.assertRuleMatchesAll('snapshot_join_dates', [
            '2026年客户快照与资产日期如何关联', '客户表和交易表使用不同期间',
        ])

    def test_distribution_projection_synonyms(self):
        self.assertRuleMatchesAll('distribution_projection', [
            '各年龄段资产分布', '分布各产品的持仓市值',
        ])

    def test_computed_column_alias_synonyms(self):
        self.assertRuleMatchesAll('computed_column_alias', [
            '两个客户群平均持仓市值差值', '各分公司钻石客户占比', '各职业客户数量',
        ])

    def test_product_category_output_synonyms(self):
        self.assertRuleMatchesAll('product_category_output', [
            '这些客户持有的产品属于哪些产品大类', '这些客户持有产品的分类情况',
        ])

    def test_explicit_product_category_level_synonyms(self):
        self.assertRuleMatchesAll('explicit_product_category_level', [
            '各产品一级分类的客户数', '产品二级分类交易金额排名',
            '按一级分类汇总市值', '按二级分类统计交易额',
        ])

    def test_generic_product_classification_does_not_force_two_levels(self):
        matched = match_business_rules('产品二级分类交易金额排名')
        self.assertNotIn('product_category_output', matched)
        self.assertIn('explicit_product_category_level', matched)

    def test_product_penetration_population_synonyms(self):
        self.assertRuleMatchesAll('product_penetration_population', [
            '各产品一级分类的客户渗透率', '渗透率按产品分类排名',
        ])

    def test_average_holding_population_synonyms(self):
        self.assertRuleMatchesAll('average_holding_population', [
            '男女客户平均持仓市值差值', '按年龄段统计持仓金额平均值',
        ])

    def test_inclusive_age_wording_synonyms(self):
        self.assertRuleMatchesAll('inclusive_age_wording', [
            '60岁以上的女性客户', '年龄在60岁以上的钻石卡客户', '50岁及以下客户',
        ])

    def test_customer_ranking_column_order_synonyms(self):
        self.assertRuleMatchesAll('customer_ranking_column_order', [
            '交易金额前10的客户及客户等级', '客户号总资产排名前20',
        ])

    def test_customer_region_distribution_synonyms(self):
        self.assertRuleMatchesAll('customer_region_distribution', [
            '满足条件客户的省份分布', '高净值客户城市分布',
        ])

    def test_difference_only_projection_synonyms(self):
        self.assertRuleMatchesAll('difference_only_projection', [
            '白金卡与金卡平均持仓市值差值', '两个群体的资产之差',
        ])

    def test_branch_join_key_synonyms(self):
        self.assertRuleMatchesAll('branch_join_key', [
            '各营业部客户买入金额', '交易金额的营业部排名',
        ])

    def test_ratio_query_optimisation_synonyms(self):
        self.assertRuleMatchesAll('ratio_query_optimisation', [
            '持仓市值大于总资产50%的客户', '持仓占总资产比例超过一半',
        ])

    def test_independent_condition_synonyms(self):
        self.assertRuleMatchesAll('independent_conditions', [
            '持有ETF且Q1有交易的客户', '持仓ETF同时在一季度发生交易的客户',
        ])


if __name__ == '__main__':
    unittest.main()
