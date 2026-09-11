"""汇总同一评测集的多次运行，报告平均值、最低值和波动范围。"""
import argparse
import json
import statistics
from pathlib import Path


METRICS = ('value_match_rate', 'schema_match_rate', 'overall_success_rate')


def summarise(paths):
    runs = [(path, json.loads(path.read_text(encoding='utf-8'))) for path in paths]
    if not runs:
        raise ValueError('没有可汇总的评测结果')
    compatibility_fields = (
        'evaluation_suite', 'evaluation_rules_version', 'question_bank_sha256',
        'data_snapshot_id', 'data_snapshot_manifest_sha256', 'prompt_sha256',
        'code_snapshot_sha256',
    )
    reference = runs[0][1]['metadata']
    for path, run in runs[1:]:
        mismatches = [
            field for field in compatibility_fields
            if run['metadata'].get(field) != reference.get(field)
        ]
        if mismatches:
            raise ValueError(f'{path.name} 与首份报告配置不同：{", ".join(mismatches)}')

    metrics = {}
    for metric in METRICS:
        values = [float(run['summary'][metric]) for _, run in runs]
        metrics[metric] = {
            'mean': statistics.fmean(values),
            'minimum': min(values),
            'maximum': max(values),
            'range': max(values) - min(values),
        }
    return {
        'suite': reference.get('evaluation_suite'),
        'runs': len(runs),
        'metrics': metrics,
        'files': [path.name for path, _ in runs],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = summarise(args.paths)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
        print(f'多次运行汇总已写入：{args.output}')
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
