"""Read-time projection of enterprise statement modules into the existing API shape."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from .finance_extract import UNIT_SCALES, normalize_source_number
from .statement_checks import evaluate_statement_checks
from .statement_tables import ALIASES


def _increment(raw):
    text = str(raw).strip().replace(",", "")
    decimals = len(text.rsplit(".", 1)[1]) if "." in text else 0
    return format(Decimal(1).scaleb(-decimals), "f")


def _statement_type(module):
    explicit = module.request_params.get("statement_type")
    if explicit:
        return explicit
    return {"资产负债表": "balance_sheet", "利润表": "income_statement", "现金流量表": "cash_flow_statement"}.get(module.module_name)


def _formula_status(checks):
    if any(check["status"] == "conflict" for check in checks):
        return "warning"
    if checks and all(check["status"] == "passed" for check in checks):
        return "passed"
    return "not_checked"


def enterprise_statement_views(import_record, module_rows):
    result = []
    for module in sorted(module_rows, key=lambda item: item.module_order if hasattr(item, "module_order") else 0):
        statement_type = _statement_type(module)
        if not statement_type:
            continue
        parsed = module.parsed_payload or {}
        periods, rows = parsed.get("periods") or [], parsed.get("rows") or []
        unit = module.request_params.get("unit") or module.request_params.get("raw_unit") or "元"
        scale = UNIT_SCALES.get(unit)
        for period_index, period in enumerate(periods):
            items = []
            for row_index, row in enumerate(rows):
                values = row.get("values") or []
                raw = values[period_index] if period_index < len(values) else None
                source_name = str(row.get("name") or row.get("key") or "")
                concept = ALIASES.get(source_name)
                mapping = "mapped" if concept else "unmapped"
                if not concept:
                    concept = "disclosed_" + hashlib.sha256(source_name.encode()).hexdigest()[:32]
                normalized = None
                if raw not in (None, "") and scale is not None:
                    try:
                        normalized = format(normalize_source_number(str(raw)) * scale, "f")
                    except ValueError:
                        pass
                evidence = {
                    "mapping_state": mapping, "source_increment": _increment(raw) if normalized is not None else None,
                    "response_sha256": module.response_sha256, "module_key": module.module_key,
                    "row": row_index, "period_column": period_index, "source_key": row.get("key"),
                }
                item_id = "ent_" + hashlib.sha256(f"{import_record.id}:{module.module_key}:{row_index}:{period_index}".encode()).hexdigest()[:24]
                items.append({
                    "id": item_id, "concept": concept, "source_name": source_name, "raw_value": raw,
                    "raw_unit": row.get("unit") or unit, "normalized_value": normalized,
                    "source_text": source_name, "source_start_line": None, "source_end_line": None,
                    "status": "source_verified" if normalized is not None else "source_value_not_found",
                    "evidence": evidence, "confirmed_by": None, "confirmed_at": None, "confirmation_reason": None,
                })
            statement_id = "enterprise_" + hashlib.sha256(f"{import_record.id}:{module.module_key}:{period_index}".encode()).hexdigest()[:24]
            view = {
                "id": statement_id, "run_id": None, "document_id": None, "conversion_id": None,
                "source_type": "enterprise_warning", "statement_type": statement_type,
                "entity": module.request_params.get("company_name", "企业预警通"),
                "scope": module.request_params.get("mergeRange", "unknown"), "period": period,
                "period_normalized": period, "period_kind": "instant" if statement_type == "balance_sheet" else "duration",
                "currency": module.request_params.get("displayCurrency", "CNY"), "raw_unit": unit,
                "unit_scale": format(scale, "f") if scale is not None else None, "state": "imported", "issues": [],
                "items": items, "source_status": "source_verified", "source_issues": [],
                "semantic_review_count": 0, "manual_review_required": False,
            }
            checks = evaluate_statement_checks(view)
            view.update(checks=checks, formula_status=_formula_status(checks))
            result.append(view)
    return result
