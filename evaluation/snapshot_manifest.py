"""生成或核验不含业务明细的数据库快照清单。"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


EVALUATION_DIR = Path(__file__).resolve().parent
PROJECT_DIR = EVALUATION_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

import psycopg2

from config import DB_CONFIG, SQL_STATEMENT_TIMEOUT_MS
from metadata_tools import METADATA


DEFAULT_PATH = EVALUATION_DIR / 'data_snapshot_manifest.json'


def _schema_hash(columns):
    payload = json.dumps(columns, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _live_schema_hash(cursor, table_name):
    cursor.execute(
        """SELECT column_name, data_type, udt_name, ordinal_position
           FROM information_schema.columns
           WHERE table_schema = current_schema() AND table_name = %s
           ORDER BY ordinal_position""",
        (table_name,),
    )
    columns = [list(row) for row in cursor.fetchall()]
    if not columns:
        raise RuntimeError(f'数据库中未找到表：{table_name}')
    return _schema_hash(columns)


def collect_profile(connection):
    """记录表行数、分区边界与元数据字段签名，不读取或保存业务明细。"""
    tables = []
    with connection.cursor() as cursor:
        cursor.execute('SET statement_timeout = %s', (SQL_STATEMENT_TIMEOUT_MS,))
        for table in sorted(METADATA['tables'], key=lambda item: item['table_name']):
            table_name = table['table_name']
            schema_sha256 = _live_schema_hash(cursor, table_name)
            partition_key = table.get('partition_key')
            if partition_key:
                cursor.execute(
                    f'SELECT COUNT(*), MIN({partition_key}), MAX({partition_key}) FROM {table_name}'
                )
                row_count, partition_min, partition_max = cursor.fetchone()
            else:
                cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
                row_count = cursor.fetchone()[0]
                partition_min = partition_max = None
            tables.append({
                'table': table_name,
                'row_count': row_count,
                'partition_key': partition_key,
                'partition_min': partition_min,
                'partition_max': partition_max,
                'schema_sha256': schema_sha256,
            })
    return tables


def build_manifest():
    with psycopg2.connect(**DB_CONFIG) as connection:
        connection.set_session(readonly=True, autocommit=True)
        tables = collect_profile(connection)
    return {
        'version': '1.0',
        'snapshot_id': os.getenv(
            'EVALUATION_DATA_SNAPSHOT', 'customer_marketing_2026Q1_20260331'
        ),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'profile_scope': 'table row counts, partition bounds and schema hashes; no row data',
        'tables': tables,
    }


def comparable(manifest):
    return {
        'version': manifest.get('version'),
        'snapshot_id': manifest.get('snapshot_id'),
        'tables': manifest.get('tables'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true', help='写入当前数据库快照清单')
    parser.add_argument('--verify', action='store_true', help='与已有清单比较')
    parser.add_argument('--path', type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    if args.write == args.verify:
        parser.error('必须且只能指定 --write 或 --verify')

    current = build_manifest()
    if args.write:
        args.path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
        )
        print(f'数据库快照清单已写入：{args.path}')
        return

    expected = json.loads(args.path.read_text(encoding='utf-8'))
    if comparable(current) != comparable(expected):
        print('数据库快照核验失败：当前表行数、分区边界或字段签名与清单不同')
        raise SystemExit(1)
    print('数据库快照核验通过')


if __name__ == '__main__':
    main()
