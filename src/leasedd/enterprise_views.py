"""Read-time projection of enterprise statement modules into the existing API shape."""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal

from .finance_extract import UNIT_SCALES, normalize_source_number
from .statement_checks import evaluate_statement_checks
from .statement_tables import ALIASES, clean_label


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
        metadata = parsed.get("metadata") or {}
        export_headers = metadata.get("headExport") or []
        unit = module.request_params.get("unit") or module.request_params.get("raw_unit") or "元"
        for header in export_headers:
            match = re.search(r"[（(]([^（）()]+)[）)]$", str(header))
            if match and match[1] in UNIT_SCALES:
                unit = match[1]
                break
        scale = UNIT_SCALES.get(unit)
        for period_index, period in enumerate(periods):
            column_metadata = {str(row.get("key")): row.get("values", [])[period_index]
                               for row in rows if period_index < len(row.get("values") or [])
                               and row.get("key") in {"dataType", "deadline", "displayCurrency", "originalCurrency"}}
            scope_value = column_metadata.get("dataType") or module.request_params.get("mergeRange", "unknown")
            # Combined source responses also contain growth/composition columns.
            # Preserve those in the raw financial view, never project them as
            # monetary statements or feed them into accounting identities.
            if re.search(r"[%％]", str(column_metadata.get("dataType", ""))):
                continue
            scope = {"1":"consolidated", "2":"parent", "合并期末":"consolidated", "母公司期末":"parent"}.get(scope_value, scope_value)
            if scope not in {"consolidated", "parent"}: scope = "unknown"
            currency_value = column_metadata.get("displayCurrency") or module.request_params.get("displayCurrency", "unknown")
            currency = {"人民币":"CNY", "美元":"USD", "日元":"JPY", "港元":"HKD", "英镑":"GBP", "欧元":"EUR", "加拿大元":"CAD", "澳大利亚元":"AUD"}.get(currency_value, currency_value)
            if currency == "O": currency = "unknown"
            items = []
            for row_index, row in enumerate(rows):
                if row.get("key") in {"dataType", "deadline", "displayCurrency", "originalCurrency", "conversionRate", "rateType", "declareDate", "dataSource"}:
                    continue
                values = row.get("values") or []
                raw = values[period_index] if period_index < len(values) else None
                source_name = str(row.get("name") or row.get("key") or "")
                concept = ALIASES.get(clean_label(source_name))
                if statement_type == "cash_flow_statement" and row.get("key") == "130065":
                    concept = None
                mapping = "mapped" if concept else "unmapped"
                if not concept:
                    concept = "disclosed_" + hashlib.sha256(source_name.encode()).hexdigest()[:32]
                normalized = None
                item_unit = row.get("unit") or unit
                if row_index+1 < len(export_headers):
                    match = re.search(r"[（(]([^（）()]+)[）)]$", str(export_headers[row_index+1]))
                    if match: item_unit = match[1]
                item_scale = UNIT_SCALES.get(item_unit)
                if raw not in (None, "") and item_scale is not None:
                    try:
                        normalized = format(normalize_source_number(str(raw)) * item_scale, "f")
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
                    "raw_unit": item_unit, "normalized_value": normalized,
                    "source_text": source_name, "source_start_line": None, "source_end_line": None,
                    "status": "source_verified" if normalized is not None else "source_value_not_found",
                    "evidence": evidence, "confirmed_by": None, "confirmed_at": None, "confirmation_reason": None,
                })
            statement_id = "enterprise_" + hashlib.sha256(f"{import_record.id}:{module.module_key}:{period_index}".encode()).hexdigest()[:24]
            view = {
                "id": statement_id, "run_id": None, "document_id": None, "conversion_id": None,
                "source_type": "enterprise_warning", "statement_type": statement_type,
                "entity": module.request_params.get("company_name", "企业预警通"),
                "scope": scope, "period": period,
                "period_normalized": column_metadata.get("deadline") or period, "period_kind": "instant" if statement_type == "balance_sheet" else "duration",
                "currency": currency, "raw_unit": unit,
                "unit_scale": format(scale, "f") if scale is not None else None, "state": "imported", "issues": [],
                "items": items, "source_status": "source_verified", "source_issues": [],
                "semantic_review_count": 0, "manual_review_required": False,
            }
            checks = evaluate_statement_checks(view)
            view.update(checks=checks, formula_status=_formula_status(checks))
            result.append(view)
    return result
