"""Fixed, non-destructive checks over source-verified disclosed values."""
from decimal import Decimal, InvalidOperation

from .finance_extract import UNIT_SCALES


CHECKS = {
    'balance_sheet': (
        ('assets_equal_liabilities_equity', {'total_assets': 1, 'total_liabilities': -1, 'total_equity': -1}),
        ('current_plus_noncurrent_assets_equal_assets', {'total_current_assets': 1, 'total_noncurrent_assets': 1, 'total_assets': -1}),
        ('current_plus_noncurrent_liabilities_equal_liabilities', {'total_current_liabilities': 1, 'total_noncurrent_liabilities': 1, 'total_liabilities': -1}),
    ),
    'income_statement': (
        ('profit_less_tax_equals_net_profit', {'total_profit': 1, 'income_tax_expense': -1, 'net_profit': -1}),
        ('operating_plus_nonoperating_equals_total_profit', {'operating_profit': 1, 'nonoperating_income': 1, 'nonoperating_expense': -1, 'total_profit': -1}),
    ),
    'cash_flow_statement': (
        ('cash_flows_plus_fx_equal_net_increase', {'net_operating_cash_flow': 1, 'net_investing_cash_flow': 1, 'net_financing_cash_flow': 1, 'exchange_rate_effect': 1, 'net_increase_in_cash': -1}),
        ('opening_cash_plus_change_equals_ending_cash', {'beginning_cash_balance': 1, 'net_increase_in_cash': 1, 'ending_cash_balance': -1}),
    ),
}


def _verified(item):
    evidence=item.get('evidence') or {}
    verified=(item.get('status')=='source_verified' and evidence.get('mapping_state')=='mapped'
              and item.get('normalized_value') is not None and evidence.get('source_increment') is not None)
    if evidence.get('response_sha256') is not None:
        verified=verified and all(evidence.get(key) is not None for key in ('module_key','row','period_column'))
    return verified


def _tolerance(item):
    scale=UNIT_SCALES.get(item.get('raw_unit'))
    if scale is None:raise ValueError('formula_unit_unverified')
    return Decimal(item['evidence']['source_increment'])*scale/Decimal(2)


def evaluate_statement_checks(statement):
    """Evaluate applicable equations without mutating statements or items."""
    results=[];items=statement.get('items') or []
    for code,coefficients in CHECKS.get(statement.get('statement_type'),()):
        involved=list(coefficients);by_concept={concept:[] for concept in involved}
        for item in items:
            if item.get('concept') in by_concept:by_concept[item['concept']].append(item)
        missing=[concept for concept in involved if not by_concept[concept]]
        selected={concept:candidates[0] for concept,candidates in by_concept.items()
                  if len(candidates)==1 and _verified(candidates[0])}
        unverified=[concept for concept in involved if by_concept[concept] and concept not in selected]
        check={'code':code,'entity':statement.get('entity'),'scope':statement.get('scope'),
               'period':statement.get('period_normalized') or statement.get('period'),
               'currency':statement.get('currency'),'difference':None,'tolerance':None,
               'missing_concepts':missing,'involved_concepts':involved,'evidence_locators':[]}
        if missing:
            check['status']='not_checked_missing_disclosure'
        elif unverified:
            check['status']='not_checked_unverified_source'
        else:
            try:
                difference=sum((Decimal(selected[concept]['normalized_value'])*coefficient
                                for concept,coefficient in coefficients.items()),Decimal(0))
                tolerance=sum((_tolerance(selected[concept]) for concept in involved),Decimal(0))
            except (InvalidOperation,ValueError,KeyError):
                check['status']='not_checked_unverified_source'
            else:
                check['difference']=format(difference,'f');check['tolerance']=format(tolerance,'f')
                check['status']='passed' if abs(difference)<=tolerance else 'conflict'
                check['evidence_locators']=[selected[concept]['evidence'].get('cell') for concept in involved]
                if all(selected[concept].get('id') for concept in involved):
                    check['item_ids']=[selected[concept]['id'] for concept in involved]
        results.append(check)
    return results
