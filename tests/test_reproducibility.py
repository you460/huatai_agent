import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation import evaluate, snapshot_manifest, summarize_runs


class ReproducibilityTest(unittest.TestCase):
    @patch.dict('os.environ', {'EVALUATION_VERIFY_SNAPSHOT': '0'})
    def test_snapshot_preflight_can_be_explicitly_disabled_for_local_debugging(self):
        self.assertEqual(evaluate.verify_data_snapshot(), 'disabled')

    def test_schema_hash_changes_with_database_column_type(self):
        first = snapshot_manifest._schema_hash([['pty_id', 'character varying', 'varchar', 1]])
        changed = snapshot_manifest._schema_hash([['pty_id', 'text', 'text', 1]])
        self.assertNotEqual(first, changed)

    def test_snapshot_comparison_ignores_generation_time(self):
        base = {
            'version': '1.0', 'snapshot_id': 'snapshot-a',
            'generated_at': 'first', 'tables': [{'table': 't', 'row_count': 1}],
        }
        later = {**base, 'generated_at': 'second'}
        self.assertEqual(
            snapshot_manifest.comparable(base), snapshot_manifest.comparable(later)
        )

    def test_manifest_hash_is_stable_when_only_generation_time_changes(self):
        original_path = evaluate.SNAPSHOT_MANIFEST_PATH
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            base = {
                'version': '1.0', 'snapshot_id': 'snapshot-a',
                'generated_at': 'first', 'tables': [{'table': 't', 'row_count': 1}],
            }
            path.write_text(json.dumps(base), encoding='utf-8')
            evaluate.SNAPSHOT_MANIFEST_PATH = path
            try:
                first = evaluate._snapshot_manifest_hash()
                path.write_text(
                    json.dumps({**base, 'generated_at': 'second'}), encoding='utf-8'
                )
                second = evaluate._snapshot_manifest_hash()
            finally:
                evaluate.SNAPSHOT_MANIFEST_PATH = original_path
        self.assertEqual(first, second)

    def test_snapshot_comparison_detects_data_profile_change(self):
        base = {
            'version': '1.0', 'snapshot_id': 'snapshot-a',
            'tables': [{'table': 't', 'row_count': 1}],
        }
        changed = {
            **base, 'tables': [{'table': 't', 'row_count': 2}],
        }
        self.assertNotEqual(
            snapshot_manifest.comparable(base), snapshot_manifest.comparable(changed)
        )

    def test_multi_run_summary_reports_mean_minimum_and_range(self):
        metadata = {
            'evaluation_suite': 'compact90', 'evaluation_rules_version': '2.6',
            'question_bank_sha256': 'q', 'data_snapshot_id': 'd',
            'data_snapshot_manifest_sha256': 'm', 'prompt_sha256': 'p',
            'code_snapshot_sha256': 'c',
        }
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for index, score in enumerate((100.0, 98.0, 99.0)):
                path = Path(folder) / f'run-{index}.json'
                path.write_text(json.dumps({
                    'metadata': metadata,
                    'summary': {
                        'value_match_rate': score,
                        'schema_match_rate': score,
                        'overall_success_rate': score,
                    },
                }), encoding='utf-8')
                paths.append(path)
            summary = summarize_runs.summarise(paths)

        self.assertEqual(summary['runs'], 3)
        self.assertEqual(summary['metrics']['overall_success_rate']['mean'], 99.0)
        self.assertEqual(summary['metrics']['overall_success_rate']['minimum'], 98.0)
        self.assertEqual(summary['metrics']['overall_success_rate']['range'], 2.0)

    def test_multi_run_summary_rejects_incompatible_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for index, prompt_hash in enumerate(('a', 'b')):
                path = Path(folder) / f'run-{index}.json'
                path.write_text(json.dumps({
                    'metadata': {
                        'evaluation_suite': 'compact90',
                        'evaluation_rules_version': '2.6',
                        'question_bank_sha256': 'q', 'data_snapshot_id': 'd',
                        'data_snapshot_manifest_sha256': 'm',
                        'prompt_sha256': prompt_hash, 'code_snapshot_sha256': 'c',
                    },
                    'summary': {metric: 100 for metric in summarize_runs.METRICS},
                }), encoding='utf-8')
                paths.append(path)
            with self.assertRaises(ValueError):
                summarize_runs.summarise(paths)


if __name__ == '__main__':
    unittest.main()
