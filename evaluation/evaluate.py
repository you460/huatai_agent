import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass


EVALUATION_DIR = Path(__file__).resolve().parent
PROJECT_DIR = EVALUATION_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

from main import execute_sql, run_agent

try:
    from main import SYSTEM_PROMPT
except ImportError:  # 单元测试可注入只包含接口函数的最小 main 模块
    SYSTEM_PROMPT = ''


RULES_VERSION = '2.6'
PROMPT_VERSION = os.getenv('EVALUATION_PROMPT_VERSION', 'main.SYSTEM_PROMPT.v9')
SAMPLE_ROWS = 5
CONTRACTS_PATH = EVALUATION_DIR / 'field_contracts.json'
SUITES_PATH = EVALUATION_DIR / 'suites.json'
SNAPSHOT_MANIFEST_PATH = EVALUATION_DIR / 'data_snapshot_manifest.json'


def _load_contracts():
    with CONTRACTS_PATH.open(encoding='utf-8') as f:
        return json.load(f)


FIELD_CONTRACTS = _load_contracts()


SEMANTIC_ALIASES = {
    'branch_company': ['up_org_name', '分公司', '分公司名称'],
    'branch_office': ['org_name', '营业部', '营业部名称'],
    'customer_id': ['pty_id', '客户号', '客户id'],
    'gender': ['gender_name', 'gender', '性别'],
    'customer_level': ['cust_lvl', 'cust_lvl_name', '客户等级'],
    'education': ['edu_name', 'edu_level', 'education', 'education_level', '学历', '学历层级', '教育程度'],
    'profession': ['prof_name', 'profession', '职业', '职业类型'],
    'account_status': ['status_name', 'account_status', '账户状态'],
    'account_source': ['sys_source', 'sys_source_name', 'account_type', 'account_source', '账户类型', '账户来源'],
    'product_id': ['prdt_id', '产品id'],
    'product_name': ['prdt_name', '产品名称'],
    'product_primary_category': ['up_prdt_type_name', '产品一级分类', '产品一级类别', '一级分类', '一级类别', '产品大类'],
    'product_secondary_category': ['prdt_type_name', '产品二级分类', '产品二级类别', '二级分类', '二级类别', '产品子类'],
    'province': ['prov_name', '省份'],
    'city': ['city_name', '城市'],
    'customer_count': ['cust_cnt', 'male_cnt', 'female_cnt', 'female_cust_cnt', 'male_cust_cnt', '高净值客户数量', '客户数', '客户数量'],
    'product_count': ['prdt_cnt', '产品数', '产品数量'],
    'transaction_count': ['trade_cnt', '成交笔数', '交易笔数'],
    'transaction_amount': ['tran_amt', 'tran_tot', 'tot_tran_amt', 'total_amt', 'total_tran_amt', 'total_trade_amt', '交易金额', '交易额', '总交易金额'],
    'buy_amount': ['buy_amt', 'tot_buy_amt', 'total_buy_amt', '总买入金额', '买入金额'],
    'sell_amount': ['sell_amt', 'tot_sell_amt', 'total_sell_amt', '总卖出金额', '卖出金额'],
    'asset_total': ['tot_aset', 'total_aset', '资产总额', '总资产', '总资产合计'],
    'asset_begin': ['bgn_aset', 'begin_aset', 'begin_asset', '期初总资产', '期初资产'],
    'asset_end': ['end_aset', 'end_asset', '期末总资产', '期末资产'],
    'asset_average': ['avg_aset', '平均总资产', '平均资产'],
    'cash_balance_normal': ['tot_nm_bal', 'nm_bal', '普通账户现金资产合计', '普通账户现金资产'],
    'cash_balance_credit': ['tot_fc_bal', 'fc_bal', '信用账户现金资产合计', '信用账户现金资产'],
    'asset_inflow': ['aset_in', 'inflow', '资金流入', '资金转入'],
    'asset_outflow': ['aset_out', 'outflow', '资金流出', '资金转出'],
    'asset_difference': ['aset_diff', '总资产差值'],
    'profit_loss': ['aset_pft', 'profit', 'pft', 'profit_loss', 'pnl', '盈亏'],
    'market_value': ['tot_mkt_val', 'total_mkt_val', 'mkt_val', 'market_value', 'tot_hold_val', '持仓市值', '持仓总市值', '期末持仓市值', '总市值'],
    'market_value_difference': ['hold_diff', '持仓市值差值'],
    'age_average': ['avg_age', '平均年龄'],
    'age_group': ['age_type', 'cust_age_type', 'age_group', 'age_grp', '年龄段'],
    'diamond_ratio': ['diamond_ratio', '钻石客户占比', '钻石卡客户占比'],
    'commission_rate': ['avg_rake_rate', 'rake_rate', 'commission_rate', 'trade_rake_rate', '交易佣金率', '佣金率', '整体交易佣金率'],
    'net_buy_amount': ['net_buy', 'net_buy_amt', '净买入金额'],
    'ratio': ['ratio', 'penetration', 'penetration_rate', '占比', '渗透率'],
}


def _normalise_name(value):
    return re.sub(r'[\s_\-]', '', str(value)).casefold()


def _semantic_for_column(column):
    name = _normalise_name(column)
    for semantic, aliases in SEMANTIC_ALIASES.items():
        if name in {_normalise_name(alias) for alias in aliases}:
            return semantic
    if name.endswith('cnt') or name == 'count':
        return 'generic_count'
    if 'tran' in name or '交易' in name:
        return 'transaction_amount'
    if 'aset' in name or '资产' in name:
        return 'asset_total'
    if 'ratio' in name or 'rate' in name or '占比' in name:
        return 'ratio'
    return f'column:{name}'


def _top_level_select_expressions(sql):
    """提取最终 SELECT 的顶层表达式；只用于字段语义推断，不改写 SQL。"""
    if not sql:
        return []
    depth = 0
    quote = None
    select_positions = []
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote:
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in "'\"":
            quote = char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth = max(depth - 1, 0)
        elif depth == 0 and re.match(r'(?i)select\b', sql[index:]):
            select_positions.append(index)
        index += 1
    if not select_positions:
        return []
    start = select_positions[-1] + len('select')
    depth = 0
    quote = None
    end = len(sql)
    for index in range(start, len(sql)):
        char = sql[index]
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth = max(depth - 1, 0)
        elif depth == 0 and re.match(r'(?i)from\b', sql[index:]):
            end = index
            break
    segment = sql[start:end]
    expressions, current, depth, quote = [], [], 0, None
    for char in segment + ',':
        if quote:
            current.append(char)
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
            current.append(char)
        elif char == '(':
            depth += 1
            current.append(char)
        elif char == ')':
            depth = max(depth - 1, 0)
            current.append(char)
        elif char == ',' and depth == 0:
            expressions.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
    return expressions


def _semantic_for_expression(expression):
    """从聚合表达式推断业务语义，避免 PostgreSQL 的 sum/round 默认列名造成误判。"""
    expression = expression or ''
    name = _normalise_name(expression)
    if not name:
        return None
    if '/' in expression and ('count' in name or 'ratio' in name or 'rate' in name):
        return 'ratio'
    if 'mktval' in name or 'marketvalue' in name or 'holdval' in name:
        if '-' in expression or 'subtract' in name:
            return 'market_value_difference'
        return 'market_value'
    if ('-' in expression and ('aset' in name or 'asset' in name)):
        return 'asset_difference'
    if 'avg' in name and ('aset' in name or 'asset' in name):
        return 'asset_average'
    if 'buyamt' in name and 'sellamt' not in name:
        if '-' in expression or 'netbuy' in name:
            return 'net_buy_amount'
        return 'buy_amount'
    if 'sellamt' in name and 'buyamt' not in name:
        return 'sell_amount'
    if ('buyamt' in name and 'sellamt' in name) or 'tranamt' in name or 'tradeamt' in name:
        return 'transaction_amount'
    if 'avg' in name and ('custage' in name or 'age' in name):
        return 'age_average'
    if 'nm_bal' in expression.lower() or 'nmbal' in name:
        return 'cash_balance_normal'
    if 'fc_bal' in expression.lower() or 'fcbal' in name:
        return 'cash_balance_credit'
    if 'cashin' in name or 'tranin' in name or 'assignin' in name:
        return 'asset_inflow'
    if 'cashout' in name or 'tranout' in name or 'assignout' in name:
        return 'asset_outflow'
    if 'nm_tot_aset' in expression.lower() or 'fc_pur_aset' in expression.lower() or 'totaset' in name:
        return 'asset_total'
    if name.startswith('count') or 'countdistinct' in name:
        if 'ptyid' in name or 'custid' in name:
            return 'customer_count'
        if 'prdtid' in name or 'productid' in name:
            return 'product_count'
        return 'generic_count'
    if 'max' in name and ('custage' in name or 'age' in name):
        return 'max_age'
    return None


def _column_semantic(column, expression=None, contract=None):
    """优先识别明确的业务维度；未知别名再回退到 SQL 表达式。"""
    normalised = _normalise_name(column)
    explicit_semantic = next(
        (semantic for semantic, aliases in SEMANTIC_ALIASES.items()
         if normalised in {_normalise_name(alias) for alias in aliases}),
        None,
    )
    from_name = explicit_semantic or _semantic_for_column(column)
    if from_name in ('branch_company', 'branch_office'):
        return from_name
    if explicit_semantic:
        return from_name
    if contract:
        contract_aliases = {_normalise_name(alias) for alias in contract.get('aliases', [])}
        if _normalise_name(column) in contract_aliases:
            return contract['semantic']
    from_expression = _semantic_for_expression(expression)
    if (from_expression == 'ratio' and contract and
            contract['semantic'] in ('ratio', 'diamond_ratio')):
        return contract['semantic']
    return from_expression or from_name


def _count_semantic_from_sql(sql):
    """COUNT(*) 无别名时，用查询对象区分客户、产品和成交笔数。"""
    text = (sql or '').casefold()
    if 'dim_product' in text or 'prdt_' in text:
        return 'product_count'
    if 'dwd_cust_tran' in text and ('count(' in text or 'count (' in text):
        return 'transaction_count'
    if 'pty_id' in text or 'cust_' in text or 'ads_cust' in text:
        return 'customer_count'
    return None


def _aliases_for(semantic, column):
    aliases = list(SEMANTIC_ALIASES.get(semantic, []))
    if semantic == 'generic_count':
        aliases.extend(['count', 'cnt', column])
    elif semantic.startswith('column:'):
        aliases.append(column)
    else:
        aliases.append(column)
    return aliases


def _field_contracts(question, standard_columns, standard_sql=None):
    configured = FIELD_CONTRACTS.get('questions', {}).get(str(question.get('id')), {})
    fields = configured.get('fields')
    if fields:
        return fields, configured.get('order')

    fields = []
    expressions = _top_level_select_expressions(standard_sql)
    for index, column in enumerate(standard_columns):
        semantic = _column_semantic(column, expressions[index] if index < len(expressions) else None)
        if semantic == 'generic_count':
            semantic = _count_semantic_from_sql(standard_sql) or semantic
        fields.append({
            'semantic': semantic,
            'aliases': _aliases_for(semantic, column),
        })
    return fields, configured.get('order')


def _round_half_up(value, nd=2):
    try:
        return float(Decimal(str(value)).quantize(
            Decimal('1e{}'.format(-nd)), rounding=ROUND_HALF_UP
        ))
    except Exception:
        try:
            return float(value)
        except Exception:
            return value


def values_equal(val1, val2):
    if val1 is None and val2 is None:
        return True
    if val1 is None or val2 is None:
        return False
    if hasattr(val1, 'quantize'):
        val1 = float(val1)
    if hasattr(val2, 'quantize'):
        val2 = float(val2)
    if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
        return _round_half_up(val1, 2) == _round_half_up(val2, 2) or abs(val1 - val2) <= 0.01
    if isinstance(val1, str) and isinstance(val2, str):
        # 严格限定的业务枚举等价关系。只折叠同一字段的代码与展示名称，
        # 不做模糊中文匹配，避免把不同业务维度误判为相同。
        enum_values = {
            'nm': 'normal_account', '普通账户': 'normal_account',
            'fc': 'credit_account', '信用账户': 'credit_account',
        }
        enum1 = enum_values.get(val1.strip().casefold())
        enum2 = enum_values.get(val2.strip().casefold())
        if enum1 is not None or enum2 is not None:
            return enum1 is not None and enum1 == enum2
        numeric_pattern = r'[-+]?(?:0|[1-9]\d*)(?:\.\d+)?'
        if re.fullmatch(numeric_pattern, val1.strip()) and re.fullmatch(numeric_pattern, val2.strip()):
            number1, number2 = Decimal(val1.strip()), Decimal(val2.strip())
            return (
                _round_half_up(number1, 2) == _round_half_up(number2, 2)
                or abs(number1 - number2) <= Decimal('0.01')
            )
        interval1 = _normalise_interval_label(val1)
        interval2 = _normalise_interval_label(val2)
        if interval1 is not None or interval2 is not None:
            return interval1 is not None and interval1 == interval2
    return val1 == val2


def _normalise_interval_label(value):
    """把数学区间和常见中文区间标签归一为（下界, 是否含下界, 上界, 是否含上界）。"""
    text = re.sub(r'\s+|岁', '', str(value)).replace('，', ',')
    mathematical = re.fullmatch(r'([\[(])([^,]*),([^\])]*)?([\])])', text)
    if mathematical:
        lower_text, upper_text = mathematical.group(2), mathematical.group(3)
        try:
            lower = Decimal(lower_text) if lower_text else None
            upper = Decimal(upper_text) if upper_text else None
        except Exception:
            return None
        return lower, mathematical.group(1) == '[', upper, mathematical.group(4) == ']'

    symbolic = re.fullmatch(r'(<=|>=|<|>)([-+]?\d+(?:\.\d+)?)', text)
    if symbolic:
        operator, boundary = symbolic.group(1), Decimal(symbolic.group(2))
        if operator in ('>=', '>'):
            return boundary, operator == '>=', None, False
        return None, False, boundary, operator == '<='

    discrete = re.fullmatch(r'([-+]?\d+)-([-+]?\d+)', text)
    if discrete:
        lower, inclusive_upper = Decimal(discrete.group(1)), Decimal(discrete.group(2))
        return lower, True, inclusive_upper + 1, False

    inclusive_above = re.fullmatch(r'([-+]?\d+)(?:及以上|以上)', text)
    if inclusive_above:
        return Decimal(inclusive_above.group(1)), True, None, False

    comparisons = []
    for part in text.split(','):
        match = re.fullmatch(r'(大于等于|不少于|小于等于|不超过|大于|超过|小于|不足)([-+]?\d+(?:\.\d+)?)', part)
        if not match:
            comparisons = []
            break
        comparisons.append((match.group(1), Decimal(match.group(2))))
    if comparisons:
        lower = upper = None
        lower_inclusive = upper_inclusive = False
        for operator, boundary in comparisons:
            if operator in ('大于等于', '不少于'):
                lower, lower_inclusive = boundary, True
            elif operator in ('大于', '超过'):
                lower, lower_inclusive = boundary, False
            elif operator in ('小于等于', '不超过'):
                upper, upper_inclusive = boundary, True
            else:
                upper, upper_inclusive = boundary, False
        return lower, lower_inclusive, upper, upper_inclusive
    return None


def _ordering_value_equal(actual, expected):
    """排序键中的数值（含JSON中的数值字符串）使用统一的0.01容差。"""
    try:
        actual_number = Decimal(str(actual))
        expected_number = Decimal(str(expected))
    except Exception:
        return values_equal(actual, expected)
    return (
        _round_half_up(actual_number, 2) == _round_half_up(expected_number, 2)
        or abs(actual_number - expected_number) <= Decimal('0.01')
    )


def _rows_equal(row1, row2):
    return len(row1) == len(row2) and all(
        values_equal(value1, value2) for value1, value2 in zip(row1, row2)
    )


def _requires_order(question):
    return bool(re.search(r'排名|前\s*\d+|最高|最低|从高到低|从低到高|降序|升序', question))


def _serialise(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_serialise(item) for item in value]
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialise(item) for key, item in value.items()}
    return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)


def _result_hash(rows):
    canonical_rows = sorted(
        json.dumps(_serialise(row), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        for row in rows
    )
    return hashlib.sha256('\n'.join(canonical_rows).encode('utf-8')).hexdigest()


def _result_snapshot(columns, rows):
    return {
        'columns': list(columns or []),
        'row_count': len(rows or []),
        'sample_rows': _serialise(list(rows or [])[:SAMPLE_ROWS]),
        'normalised_result_hash': _result_hash(rows or []),
    }


def _field_check(actual_columns, expected_columns, contracts, generated_sql=None):
    if len(actual_columns) != len(expected_columns) or len(actual_columns) != len(contracts):
        return False, {
            'difference_type': '字段语义错误',
            'summary': f'返回列数 {len(actual_columns)}，预期列数 {len(expected_columns)}',
        }

    expressions = _top_level_select_expressions(generated_sql)
    for index, (actual, expected, contract) in enumerate(zip(actual_columns, expected_columns, contracts)):
        actual_semantic = _column_semantic(
            actual, expressions[index] if index < len(expressions) else None, contract
        )
        if actual_semantic == 'generic_count':
            if contract['semantic'] in ('customer_count', 'product_count', 'transaction_count'):
                actual_semantic = contract['semantic']
            else:
                actual_semantic = _count_semantic_from_sql(generated_sql) or actual_semantic
        if actual_semantic != contract['semantic']:
            return False, {
                'difference_type': '字段语义错误',
                'summary': (
                    f'第 {index + 1} 列返回“{actual}”（语义“{actual_semantic}”），预期语义为“{contract["semantic"]}”'
                    f'（基准列“{expected}”）'
                ),
                'field_index': index,
                'expected_semantic': contract['semantic'],
                'actual_semantic': actual_semantic,
                'allowed_aliases': contract.get('aliases', []),
            }
    return True, None


def _unordered_rows_match(actual_rows, expected_rows):
    unmatched = list(expected_rows)
    for actual in actual_rows:
        for index, expected in enumerate(unmatched):
            if _rows_equal(actual, expected):
                unmatched.pop(index)
                break
        else:
            return False, actual, unmatched[:SAMPLE_ROWS]
    return not unmatched, None, unmatched[:SAMPLE_ROWS]


def _order_spec(question, contracts, configured_order):
    if configured_order:
        return configured_order
    if not _requires_order(question):
        return {'required': False}
    return {
        'required': True,
        'keys': [contracts[-1]['semantic']],
        'tie_policy': 'any',
    }


def _key_indexes(spec, contracts):
    indexes = []
    for semantic in spec.get('keys', []):
        for index, contract in enumerate(contracts):
            if contract['semantic'] == semantic:
                indexes.append(index)
                break
        else:
            raise ValueError(f'排序字段语义未出现在字段合同中: {semantic}')
    return indexes


def _has_explicit_secondary_order(sql):
    match = re.search(r'\border\s+by\s+(.+?)(?:\blimit\b|$)', sql, re.IGNORECASE | re.DOTALL)
    return bool(match and ',' in match.group(1))


def _compare_ranked_rows(actual_rows, expected_rows, indexes, tie_policy, generated_sql=None,
                         standard_sql=None):
    values_match, unexpected, remaining = _unordered_rows_match(actual_rows, expected_rows)
    if not values_match:
        return False, {
            'difference_type': '结果不一致',
            'summary': f'生成结果含不匹配行 { _serialise(unexpected) }；基准剩余样例 { _serialise(remaining) }',
        }

    if tie_policy == 'fixed':
        if not (_has_explicit_secondary_order(generated_sql or '') and
                _has_explicit_secondary_order(standard_sql or '')):
            return False, {
                'difference_type': '排序不一致',
                'summary': '固定并列顺序的题目必须在基准SQL和生成SQL中声明二级 ORDER BY',
            }
        if all(_rows_equal(actual, expected) for actual, expected in zip(actual_rows, expected_rows)):
            return True, None
        return False, {
            'difference_type': '排序不一致',
            'summary': '该题配置了固定次级排序，生成结果的行顺序与基准不一致',
        }

    expected_keys = [tuple(row[index] for index in indexes) for row in expected_rows]
    actual_keys = [tuple(row[index] for index in indexes) for row in actual_rows]
    keys_match = len(actual_keys) == len(expected_keys) and all(
        len(actual) == len(expected) and all(
            _ordering_value_equal(actual_value, expected_value)
            for actual_value, expected_value in zip(actual, expected)
        )
        for actual, expected in zip(actual_keys, expected_keys)
    )
    if not keys_match:
        return False, {
            'difference_type': '排序不一致',
            'summary': '排名主排序字段的顺序与基准不一致；并列主键内部顺序已允许不同',
            'expected_order_keys': _serialise(expected_keys[:SAMPLE_ROWS]),
            'actual_order_keys': _serialise(actual_keys[:SAMPLE_ROWS]),
        }
    return True, None


def compare_with_evidence(question, actual_columns, actual_rows, expected_columns, expected_rows,
                          generated_sql=None, standard_sql=None):
    contracts, configured_order = _field_contracts(question, expected_columns, standard_sql)
    fields_match, field_evidence = _field_check(
        actual_columns, expected_columns, contracts, generated_sql
    )

    if len(actual_rows) != len(expected_rows):
        result_match, result_evidence = False, {
            'difference_type': '结果不一致',
            'summary': f'生成结果 {len(actual_rows)} 行，基准结果 {len(expected_rows)} 行',
        }
    else:
        spec = _order_spec(question.get('question', ''), contracts, configured_order)
        if spec.get('required'):
            try:
                result_match, result_evidence = _compare_ranked_rows(
                    actual_rows, expected_rows, _key_indexes(spec, contracts),
                    spec.get('tie_policy', 'any'), generated_sql, standard_sql
                )
            except ValueError as error:
                result_match, result_evidence = False, {
                    'difference_type': '排序不一致', 'summary': str(error)
                }
        else:
            rows_match, unexpected, remaining = _unordered_rows_match(actual_rows, expected_rows)
            result_match = rows_match
            result_evidence = None if rows_match else {
                'difference_type': '结果不一致',
                'summary': f'生成结果含不匹配行 { _serialise(unexpected) }；基准剩余样例 { _serialise(remaining) }',
            }

    if fields_match and result_match:
        return True, {'field_check': {'passed': True}, 'result_check': {'passed': True}}
    primary = field_evidence or result_evidence
    return False, {
        **primary,
        'difference_types': [item['difference_type'] for item in (field_evidence, result_evidence) if item],
        'field_check': {'passed': fields_match, 'evidence': field_evidence},
        'result_check': {'passed': result_match, 'evidence': result_evidence},
    }


def compare_results(col_names1, results1, col_names2, results2, question=''):
    """兼容旧调用：只返回布尔值；新评测使用 compare_with_evidence。"""
    return compare_with_evidence(
        {'id': None, 'question': question}, col_names1, results1, col_names2, results2
    )[0]


def is_question_scored(question):
    return question.get('valid_for_scoring', True)


def parse_question_ids(value):
    return {int(item.strip()) for item in value.split(',') if item.strip()}


def load_suites():
    with SUITES_PATH.open(encoding='utf-8') as f:
        return json.load(f)


def select_suite(questions, suite_name):
    suites = load_suites()
    if suite_name not in suites['suites']:
        choices = ', '.join(sorted(suites['suites']))
        raise ValueError(f'未知评测集 {suite_name}；可选：{choices}')
    suite = suites['suites'][suite_name]
    ids = suite['question_ids']
    if ids == 'all':
        return list(questions), suite
    wanted = set(ids)
    selected = [question for question in questions if question['id'] in wanted]
    missing = wanted - {question['id'] for question in selected}
    if missing:
        raise ValueError(f'评测集包含不存在的题号：{sorted(missing)}')
    return selected, suite


def load_suite_questions(suite_name):
    suites = load_suites()
    if suite_name not in suites['suites']:
        choices = ', '.join(sorted(suites['suites']))
        raise ValueError(f'未知评测集 {suite_name}；可选：{choices}')
    suite = suites['suites'][suite_name]
    question_path = EVALUATION_DIR / suite.get('question_file', 'test_questions.json')
    with question_path.open(encoding='utf-8') as f:
        questions = json.load(f)
    selected, suite = select_suite(questions, suite_name)
    return selected, suite, question_path


def reviewed_value(question, field):
    return question.get(f'reviewed_{field}', question[field])


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_revision():
    try:
        revision = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=PROJECT_DIR, check=True,
            capture_output=True, text=True
        ).stdout.strip()
        dirty = subprocess.run(
            ['git', 'status', '--porcelain'], cwd=PROJECT_DIR, check=True,
            capture_output=True, text=True
        ).stdout.strip()
        return revision + ('+dirty' if dirty else '')
    except Exception:
        return 'unavailable'


def _code_snapshot_hash():
    digest = hashlib.sha256()
    for relative_path in (
        'app.py', 'config.py', 'main.py', 'metadata_tools.py', 'security_guard.py',
        'evaluation/evaluate.py', 'evaluation/field_contracts.json',
        'evaluation/suites.json', 'evaluation/snapshot_manifest.py',
        'metadata/metadata.json', 'requirements.txt', 'requirements-lock.txt',
    ):
        path = PROJECT_DIR / relative_path
        digest.update(relative_path.encode('utf-8'))
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def _dependency_versions():
    versions = {}
    for package in ('psycopg2-binary', 'openai', 'sqlglot', 'gradio', 'pandas'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = 'not-installed'
    return versions


def _snapshot_manifest_hash():
    if not SNAPSHOT_MANIFEST_PATH.exists():
        return None
    manifest = json.loads(SNAPSHOT_MANIFEST_PATH.read_text(encoding='utf-8'))
    stable_content = {
        'version': manifest.get('version'),
        'snapshot_id': manifest.get('snapshot_id'),
        'tables': manifest.get('tables'),
    }
    payload = json.dumps(
        stable_content, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def verify_data_snapshot():
    """正式评测前验证数据库画像，避免把不同数据上的分数混为一谈。"""
    if os.getenv('EVALUATION_VERIFY_SNAPSHOT', '1').strip().lower() in ('0', 'false', 'no'):
        return 'disabled'
    if not SNAPSHOT_MANIFEST_PATH.exists():
        raise RuntimeError(
            '缺少 evaluation/data_snapshot_manifest.json；请先运行 '
            'python evaluation/snapshot_manifest.py --write'
        )
    from evaluation.snapshot_manifest import build_manifest, comparable
    expected = json.loads(SNAPSHOT_MANIFEST_PATH.read_text(encoding='utf-8'))
    current = build_manifest()
    if comparable(current) != comparable(expected):
        raise RuntimeError(
            '数据库快照与 data_snapshot_manifest.json 不一致，评测已停止'
        )
    return 'verified'


def _run_metadata(question_path, started_at=None):
    started_at = started_at or datetime.now(timezone.utc)
    return {
        'evaluation_rules_version': RULES_VERSION,
        'field_contracts_version': FIELD_CONTRACTS.get('version', 'unversioned'),
        'question_bank_sha256': _file_hash(question_path),
        'data_snapshot_id': os.getenv(
            'EVALUATION_DATA_SNAPSHOT', 'customer_marketing_2026Q1_20260331'
        ),
        'model': {
            'name': os.getenv('DEEPSEEK_MODEL', 'deepseek-chat'),
            'temperature': os.getenv('LLM_TEMPERATURE', '0'),
            'max_retries': os.getenv('LLM_MAX_RETRIES', '3'),
            'max_agent_rounds': os.getenv('AGENT_MAX_ROUNDS', '12'),
        },
        'prompt_version': PROMPT_VERSION,
        'prompt_sha256': hashlib.sha256(SYSTEM_PROMPT.encode('utf-8')).hexdigest(),
        'code_version': _git_revision(),
        'code_snapshot_sha256': _code_snapshot_hash(),
        'artifact_sha256': {
            'metadata': _file_hash(PROJECT_DIR / 'metadata' / 'metadata.json'),
            'field_contracts': _file_hash(CONTRACTS_PATH),
            'evaluation_suites': _file_hash(SUITES_PATH),
        },
        'data_snapshot_manifest_sha256': _snapshot_manifest_hash(),
        'runtime': {
            'python': platform.python_version(),
            'implementation': platform.python_implementation(),
            'platform': platform.platform(),
            'dependencies': _dependency_versions(),
        },
        'run_started_at': started_at.isoformat(),
    }


def _detail(question, generated_sql, standard_sql, elapsed, difference_type, summary,
            generated_columns=None, generated_rows=None, standard_columns=None, standard_rows=None,
            failure_evidence=None, comparison_evidence=None):
    if comparison_evidence:
        schema_match = bool(comparison_evidence.get('field_check', {}).get('passed'))
        value_match = bool(comparison_evidence.get('result_check', {}).get('passed'))
    else:
        schema_match = difference_type == '结果一致'
        value_match = difference_type == '结果一致'
    overall_success = schema_match and value_match
    return {
        'id': question['id'],
        'difficulty': question['difficulty'],
        'source': question.get('source', 'self'),
        'base_id': question.get('base_id'),
        'variant_type': question.get('variant_type'),
        'question': reviewed_value(question, 'question'),
        'success': overall_success,
        'value_match': value_match,
        'schema_match': schema_match,
        'overall_success': overall_success,
        'valid_for_scoring': is_question_scored(question),
        'difference_type': difference_type,
        'difference_summary': summary,
        'failure_evidence': failure_evidence,
        'comparison_evidence': comparison_evidence,
        'generated_sql': generated_sql,
        'standard_sql': standard_sql,
        'field_contracts': _field_contracts(question, standard_columns or [], standard_sql)[0],
        'generated_result': _result_snapshot(generated_columns, generated_rows),
        'standard_result': _result_snapshot(standard_columns, standard_rows),
        'time_seconds': elapsed,
    }


def _match_summary(details):
    total = len(details)
    value_count = sum(item.get('value_match', False) for item in details)
    schema_count = sum(item.get('schema_match', False) for item in details)
    overall_count = sum(item.get('overall_success', False) for item in details)
    return {
        'value_match': value_count,
        'value_match_rate': value_count / total * 100 if total else 0,
        'schema_match': schema_count,
        'schema_match_rate': schema_count / total * 100 if total else 0,
        'overall_success': overall_count,
        'overall_success_rate': overall_count / total * 100 if total else 0,
    }


def _group_metrics(details, field):
    groups = {}
    for item in details:
        key = item.get(field, 'unknown')
        group = groups.setdefault(key, {
            'total': 0, 'value_match': 0, 'schema_match': 0, 'overall_success': 0,
        })
        group['total'] += 1
        for metric in ('value_match', 'schema_match', 'overall_success'):
            group[metric] += int(bool(item.get(metric)))
    return groups


def _write_replay_report(source, replay, output_path):
    yn = lambda value: '是' if value else '否'
    source_by_id = {item['id']: item for item in source['details']}
    original_field_ids = {
        item['id'] for item in source['details']
        if item.get('difference_type') == '字段语义错误'
    }
    replay_by_id = {item['id']: item for item in replay['details']}
    lines = [
        '# v2 离线重判报告', '',
        f'- 来源文件：`{replay["metadata"]["replay_of"]}`',
        f'- 评测规则版本：`{RULES_VERSION}`',
        '- 重放方式：重新执行已保存的生成 SQL 与基准 SQL，未调用模型。', '',
        '## 三项指标', '',
        '| 指标 | 通过数 | 通过率 |', '|---|---:|---:|',
        f'| value_match | {replay["summary"]["value_match"]}/{replay["summary"]["scored"]} | {replay["summary"]["value_match_rate"]:.2f}% |',
        f'| schema_match | {replay["summary"]["schema_match"]}/{replay["summary"]["scored"]} | {replay["summary"]["schema_match_rate"]:.2f}% |',
        f'| overall_success | {replay["summary"]["overall_success"]}/{replay["summary"]["scored"]} | {replay["summary"]["overall_success_rate"]:.2f}% |', '',
        '## 来源文件中的字段语义错误复核', '',
        '| 题号 | value_match | schema_match | overall_success | 变化原因 |',
        '|---:|:---:|:---:|:---:|---|',
    ]
    for question_id in sorted(original_field_ids):
        item = replay_by_id[question_id]
        original = source_by_id[question_id]
        hashes_equal = (
            original.get('generated_result', {}).get('normalised_result_hash') ==
            original.get('standard_result', {}).get('normalised_result_hash')
        )
        if item['overall_success'] and not hashes_equal:
            reason = '结果哈希不同，但逐值数值容差与排序检查通过；字段语义归一后通过'
        elif item['overall_success']:
            reason = '合理别名或聚合表达式语义归一后通过'
        elif item['schema_match'] and not item['value_match']:
            reason = item['comparison_evidence']['result_check']['evidence']['summary']
        elif item['value_match'] and not item['schema_match']:
            reason = item['comparison_evidence']['field_check']['evidence']['summary']
        else:
            reason = '字段与结果均不一致'
        reason = str(reason).replace('|', '\\|').replace('\n', ' ')
        lines.append(
            f'| {question_id} | {yn(item["value_match"])} | {yn(item["schema_match"])} | '
            f'{yn(item["overall_success"])} | {reason} |'
        )
    changed_ids = [
        item['id'] for item in replay['details']
        if any(
            bool(item.get(field)) != bool(source_by_id[item['id']].get(field))
            for field in ('value_match', 'schema_match', 'overall_success')
        )
    ]
    lines.extend([
        '', '## 本次判定变化', '',
        '| 题号 | 原差异类型 | 新差异类型 | value_match | schema_match | overall_success |',
        '|---:|---|---|:---:|:---:|:---:|',
    ])
    for question_id in sorted(changed_ids):
        original, item = source_by_id[question_id], replay_by_id[question_id]
        lines.append(
            f'| {question_id} | {original.get("difference_type", "")} | '
            f'{item.get("difference_type", "")} | {yn(item["value_match"])} | '
            f'{yn(item["schema_match"])} | {yn(item["overall_success"])} |'
        )
    lines.extend([
        '', '## 当前未通过题目', '',
        '| 题号 | 差异类型 | 差异摘要 |', '|---:|---|---|',
    ])
    for item in replay['details']:
        if item['overall_success']:
            continue
        summary = str(item['difference_summary']).replace('|', '\\|').replace('\n', ' ')
        lines.append(f'| {item["id"]} | {item["difference_type"]} | {summary} |')
    report_path = output_path.with_suffix('.md')
    report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report_path


def main(suite_name=None):
    snapshot_status = verify_data_snapshot()
    print(f'数据库快照核验: {snapshot_status}')
    suites = load_suites()
    suite_name = suite_name or os.environ.get('EVALUATION_SUITE') or suites['default_suite']
    questions, suite, question_path = load_suite_questions(suite_name)
    selected_ids = parse_question_ids(os.environ.get('QUESTION_IDS', ''))
    if selected_ids:
        questions = [q for q in questions if q['id'] in selected_ids]
        print(f"仅评测题号: {', '.join(map(str, sorted(selected_ids)))}")
    print(f'评测集: {suite_name}（{suite["description"]}）')

    started = datetime.now(timezone.utc)
    results = []
    success_count = 0
    invalid_reference_count = 0
    diff_stats = {name: {'total': 0, 'success': 0} for name in ('简单', '中等', '较难')}

    print(f'共 {len(questions)} 条测试题')
    for index, question in enumerate(questions, 1):
        text = reviewed_value(question, 'question')
        standard_sql = reviewed_value(question, 'standard_sql')
        print(f'[{index}/{len(questions)}] {question["difficulty"]} - {text}')

        if not is_question_scored(question):
            invalid_reference_count += 1
            results.append(_detail(
                question, None, standard_sql, 0, '基准SQL失败',
                question.get('reference_note', '题库标记为暂不计分')
            ))
            continue

        # 基准 SQL 是仓库内固定的受审题库；跳过用户 SQL 的 LIMIT 规则，
        # 但仍由 execute_sql 施加只读连接、超时和最大返回行数控制。
        standard_columns, standard_rows, standard_error = execute_sql(
            standard_sql, validate_sql=False
        )
        if standard_error:
            invalid_reference_count += 1
            results.append(_detail(
                question, None, standard_sql, 0, '基准SQL失败', standard_error,
                standard_columns=standard_columns, standard_rows=standard_rows
            ))
            continue

        start = time.time()
        try:
            agent_result = run_agent(text, return_result=True)
        except Exception as error:
            agent_result = None
            agent_error = str(error)
            failure_evidence = {'stage': 'run_agent', 'error': str(error)[:240]}
        else:
            agent_error = getattr(agent_result, 'message', None)
            failure_evidence = getattr(agent_result, 'details', None)
        elapsed = time.time() - start

        if not agent_result:
            difference_type = getattr(agent_result, 'kind', 'agent_generation_error')
            difference_type = {
                'agent_generation_error': 'Agent生成失败',
                'agent_execution_error': '执行失败',
                'agent_validation_error': '执行失败',
            }.get(difference_type, 'Agent生成失败')
            results.append(_detail(
                question, (failure_evidence or {}).get('sql'), standard_sql, elapsed, difference_type,
                agent_error or 'Agent 未返回可用结果',
                standard_columns=standard_columns, standard_rows=standard_rows,
                failure_evidence=failure_evidence
            ))
            diff_stats[question['difficulty']]['total'] += 1
            continue

        correct, evidence = compare_with_evidence(
            question, agent_result.columns, agent_result.rows, standard_columns, standard_rows,
            agent_result.sql, standard_sql
        )
        difference_type = '结果一致' if correct else evidence['difference_type']
        summary = '字段语义、结果值和题意要求的排序均一致' if correct else evidence['summary']
        results.append(_detail(
            question, agent_result.sql, standard_sql, elapsed, difference_type, summary,
            agent_result.columns, agent_result.rows, standard_columns, standard_rows,
            comparison_evidence=evidence
        ))
        diff_stats[question['difficulty']]['total'] += 1
        if correct:
            success_count += 1
            diff_stats[question['difficulty']]['success'] += 1

    scored_count = len(questions) - invalid_reference_count
    metadata = _run_metadata(question_path, started)
    metadata['evaluation_suite'] = suite_name
    metadata['evaluation_suite_version'] = suites.get('version', 'unversioned')
    metadata['evaluation_suite_description'] = suite['description']
    metadata['run_finished_at'] = datetime.now(timezone.utc).isoformat()
    metadata['duration_seconds'] = round((datetime.now(timezone.utc) - started).total_seconds(), 3)
    output = {
        'metadata': metadata,
        'summary': {
            'total': len(questions),
            'scored': scored_count,
            'invalid_reference': invalid_reference_count,
            'success': success_count,
            'accuracy': success_count / scored_count * 100 if scored_count else 0,
            'by_difficulty': diff_stats,
        },
        'details': results,
    }
    output['summary']['difference_counts'] = {
        difference_type: sum(item['difference_type'] == difference_type for item in results)
        for difference_type in sorted({item['difference_type'] for item in results})
    }
    output['summary'].update(_match_summary(results))
    scored_details = [item for item in results if item['valid_for_scoring']]
    output['summary']['by_source'] = _group_metrics(scored_details, 'source')
    variant_details = [item for item in scored_details if item.get('variant_type')]
    output['summary']['by_variant_type'] = _group_metrics(variant_details, 'variant_type')
    elapsed_values = [item['time_seconds'] for item in scored_details]
    output['summary']['average_agent_seconds'] = (
        sum(elapsed_values) / len(elapsed_values) if elapsed_values else 0
    )
    timestamp = started.strftime('%Y%m%dT%H%M%S%fZ')
    scope = 'subset' if selected_ids else suite_name
    output_path = EVALUATION_DIR / f'eval_results_v2_{scope}_{timestamp}.json'
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'有效计分题: {scored_count}，成功: {success_count}，准确率: {output["summary"]["accuracy"]:.1f}%')
    print(f'详细结果已保存到 {output_path.name}')


def replay_result_file(source_path):
    """不调用模型，重执既有 SQL 并按当前规则重放判定。"""
    verify_data_snapshot()
    source_path = Path(source_path)
    with source_path.open(encoding='utf-8') as f:
        source = json.load(f)
    started = datetime.now(timezone.utc)
    replayed = []
    for original in source['details']:
        question = {
            'id': original['id'], 'difficulty': original['difficulty'],
            'source': original.get('source', 'self'),
            'question': original['question'], 'valid_for_scoring': original.get('valid_for_scoring', True),
        }
        standard_sql = original.get('standard_sql')
        generated_sql = original.get('generated_sql')
        standard_columns, standard_rows, standard_error = execute_sql(standard_sql, validate_sql=False)
        if standard_error:
            replayed.append(_detail(
                question, generated_sql, standard_sql, 0, '基准SQL失败', standard_error,
                standard_columns=standard_columns, standard_rows=standard_rows
            ))
            continue
        if not generated_sql:
            difference_type = original['difference_type']
            difference_summary = original['difference_summary']
            failure_evidence = original.get('failure_evidence')
            if '未找到SELECT或WITH' in difference_summary.replace(' ', ''):
                difference_type = 'Agent生成失败'
                failure_evidence = {
                    **(failure_evidence or {}),
                    'stage': 'model_response',
                    'error': '模型响应中未找到SELECT或WITH语句',
                }
            replayed.append(_detail(
                question, None, standard_sql, 0, difference_type,
                difference_summary, standard_columns=standard_columns,
                standard_rows=standard_rows, failure_evidence=failure_evidence,
            ))
            continue
        actual_columns, actual_rows, actual_error = execute_sql(generated_sql)
        if actual_error:
            replayed.append(_detail(
                question, generated_sql, standard_sql, 0, '执行失败', actual_error,
                generated_columns=actual_columns, generated_rows=actual_rows,
                standard_columns=standard_columns, standard_rows=standard_rows,
                failure_evidence={'stage': 'sql_execution', 'error': actual_error[:240]},
            ))
            continue
        correct, evidence = compare_with_evidence(
            question, actual_columns, actual_rows, standard_columns, standard_rows,
            generated_sql, standard_sql,
        )
        replayed.append(_detail(
            question, generated_sql, standard_sql, 0,
            '结果一致' if correct else evidence['difference_type'],
            '字段语义、结果值和题意要求的排序均一致' if correct else evidence['summary'],
            actual_columns, actual_rows, standard_columns, standard_rows,
            comparison_evidence=evidence,
        ))

    scored = [item for item in replayed if item['valid_for_scoring']]
    success = sum(item['overall_success'] for item in scored)
    timestamp = started.strftime('%Y%m%dT%H%M%S%fZ')
    output = {
        'metadata': {
            **source.get('metadata', {}),
            'evaluation_rules_version': RULES_VERSION,
            'replay_of': source_path.name,
            'replay_mode': 're-execute stored SQL without model API',
            'replay_started_at': started.isoformat(),
            'replay_finished_at': datetime.now(timezone.utc).isoformat(),
        },
        'summary': {
            'total': len(replayed), 'scored': len(scored), 'success': success,
            'accuracy': success / len(scored) * 100 if scored else 0,
            'difference_counts': {
                kind: sum(item['difference_type'] == kind for item in replayed)
                for kind in sorted({item['difference_type'] for item in replayed})
            },
        },
        'details': replayed,
    }
    output['summary'].update(_match_summary(scored))
    output_path = EVALUATION_DIR / f'eval_results_v2_replay_{timestamp}.json'
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    report_path = _write_replay_report(source, output, output_path)
    print(f'离线重放完成：{output_path.name}')
    print(f'离线重判报告：{report_path.name}')
    return output_path


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--replay':
        replay_result_file(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == '--suite':
        main(sys.argv[2])
    else:
        main()
