import json
import unittest
from collections import Counter
from pathlib import Path


EVALUATION_DIR = Path(__file__).parents[1] / 'evaluation'


class GeneralizationQuestionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = json.loads(
            (EVALUATION_DIR / 'test_questions.json').read_text(encoding='utf-8')
        )
        cls.variants = json.loads(
            (EVALUATION_DIR / 'generalization_questions.json').read_text(encoding='utf-8')
        )
        cls.base_by_id = {item['id']: item for item in cls.base}

    def test_has_30_unique_questions_balanced_by_difficulty(self):
        self.assertEqual(len(self.variants), 30)
        self.assertEqual(len({item['id'] for item in self.variants}), 30)
        self.assertEqual(len({item['base_id'] for item in self.variants}), 30)
        self.assertEqual(
            Counter(item['difficulty'] for item in self.variants),
            {'简单': 10, '中等': 10, '较难': 10},
        )

    def test_each_variant_reuses_unchanged_reference_sql_and_difficulty(self):
        for item in self.variants:
            with self.subTest(id=item['id'], base_id=item['base_id']):
                base = self.base_by_id[item['base_id']]
                self.assertEqual(
                    item['standard_sql'],
                    base.get('reviewed_standard_sql') or base['standard_sql'],
                )
                self.assertEqual(item['difficulty'], base['difficulty'])
                self.assertNotEqual(item['question'].strip(), base['question'].strip())
                self.assertEqual(item['source'], 'generalization')

    def test_variant_types_cover_multiple_language_changes(self):
        kinds = {item['variant_type'] for item in self.variants}
        self.assertTrue({
            'synonym', 'word_order', 'boundary_expression', 'time_expression',
            'condition_reorder', 'ranking_expression', 'business_term',
        }.issubset(kinds))

    def test_known_strict_boundary_is_preserved(self):
        item = next(item for item in self.variants if item['base_id'] == 101)
        self.assertIn('超过40岁', item['question'])
        self.assertNotIn('40岁以上', item['question'])


if __name__ == '__main__':
    unittest.main()
