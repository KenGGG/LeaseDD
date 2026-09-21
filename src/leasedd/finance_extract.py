import re
from calendar import monthrange
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


STATEMENT_TYPES = {"balance_sheet", "income_statement", "cash_flow_statement"}
SCOPES = {"consolidated", "parent", "standalone", "unknown"}
UNIT_SCALES = {
    "元": Decimal("1"),
    "千元": Decimal("1000"),
    "万元": Decimal("10000"),
    "百万元": Decimal("1000000"),
    "亿元": Decimal("100000000"),
}
FINANCIAL_CONCEPTS = {
    "cash", "trading_financial_assets", "notes_receivable", "accounts_receivable",
    "receivables_financing", "prepayments", "other_receivables", "inventory",
    "contract_assets", "total_current_assets", "total_noncurrent_assets", "fixed_assets", "construction_in_progress",
    "right_of_use_assets", "intangible_assets", "total_assets", "short_term_borrowings",
    "notes_payable", "accounts_payable", "contract_liabilities", "other_payables",
    "current_portion_noncurrent_liabilities", "long_term_borrowings", "bonds_payable",
    "lease_liabilities", "total_current_liabilities", "total_noncurrent_liabilities", "total_liabilities", "total_equity",
    "revenue", "cost", "taxes_and_surcharges", "selling_expenses", "administrative_expenses",
    "research_and_development_expenses", "finance_expenses", "other_income",
    "investment_income", "credit_impairment_loss", "asset_impairment_loss",
    "operating_profit", "nonoperating_income", "nonoperating_expense", "total_profit", "income_tax_expense", "net_profit",
    "net_profit_attributable_to_parent", "net_profit_excluding_nonrecurring",
    "cash_received_from_sales", "operating_cash_inflows", "operating_cash_outflows",
    "net_operating_cash_flow", "net_investing_cash_flow", "net_financing_cash_flow",
    "net_increase_in_cash", "ending_cash_balance",
}


@dataclass(frozen=True)
class MarkdownChunk:
    start_line: int
    end_line: int
    text: str


def chunk_markdown(text: str, max_chars: int = 12000, overlap_lines: int = 8) -> list[MarkdownChunk]:
    if max_chars < 64:
        raise ValueError("chunk_budget_too_small")
    lines = text.splitlines() or [""]
    expanded: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, 1):
        if not line:
            expanded.append((line_no, ""))
        else:
            for offset in range(0, len(line), max_chars):
                expanded.append((line_no, line[offset:offset + max_chars]))
    chunks: list[MarkdownChunk] = []
    index = 0
    while index < len(expanded):
        used: list[tuple[int, str]] = []
        size = 0
        cursor = index
        while cursor < len(expanded):
            addition = len(expanded[cursor][1]) + (1 if used else 0)
            if used and size + addition > max_chars:
                break
            used.append(expanded[cursor]); size += addition; cursor += 1
            if size >= max_chars:
                break
        chunks.append(MarkdownChunk(used[0][0], used[-1][0], "\n".join(x[1] for x in used)))
        if cursor >= len(expanded):
            break
        if overlap_lines:
            first_line = max(1, used[-1][0] - overlap_lines + 1)
            next_index = cursor
            while next_index > index and expanded[next_index - 1][0] >= first_line:
                next_index -= 1
            index = next_index if next_index > index else cursor
        else:
            index = cursor
    return chunks


def normalize_source_number(value: str) -> Decimal:
    cleaned = value.strip().replace("，", ",").replace("（", "(").replace("）", ")")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    cleaned = re.sub(r"[\s,]", "", cleaned)
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    if not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        raise ValueError("invalid_source_number")
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid_source_number") from exc
    return -number if negative else number


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def normalize_period(value: str, statement_type: str = '') -> tuple[str, str] | None:
    value = value.strip().upper()
    match = re.fullmatch(r"(\d{4})H1", value) or re.fullmatch(r"(\d{4})年(?:1[-—–至到]6月|半年度)", value)
    if match:
        year = match.group(1)
        return f"{year}-01-01/{year}-06-30", "half_year"
    match = re.fullmatch(r"(\d{4})年(\d{1,2})[-—–至到](\d{1,2})月", value)
    if match:
        year_text, start_text, end_text = match.groups()
        year, start, end = int(year_text), int(start_text), int(end_text)
        if not 1 <= start <= end <= 12:
            return None
        period_kind = "duration"
        if (start, end) == (1, 12):
            period_kind = "year"
        elif (start, end) == (1, 6):
            period_kind = "half_year"
        elif (start, end) in ((1, 3), (4, 6), (7, 9), (10, 12)):
            period_kind = "quarter"
        return f"{year:04d}-{start:02d}-01/{year:04d}-{end:02d}-{monthrange(year, end)[1]:02d}", period_kind
    match = re.fullmatch(r"(\d{4})Q([1-4])", value)
    if match:
        year, quarter = match.groups()
        bounds = {"1": ("01-01", "03-31"), "2": ("04-01", "06-30"), "3": ("07-01", "09-30"), "4": ("10-01", "12-31")}
        start, end = bounds[quarter]
        return f"{year}-{start}/{year}-{end}", "quarter"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        if statement_type == 'balance_sheet' and value.endswith('-01-01'):
            return f'{int(value[:4])-1:04d}-12-31', 'instant'
        return value, "instant"
    match = re.fullmatch(r"(\d{4})年度", value)
    if match:
        year = match.group(1)
        return f"{year}-01-01/{year}-12-31", "year"
    return None


_NUMBER_TOKEN = re.compile(r"[（(]?\s*-?\s*\d[\d,，\s]*(?:\.\d+)?\s*[)）]?")


def _source_contains_number(raw_value: str, source: str) -> bool:
    try:
        expected = normalize_source_number(raw_value)
    except ValueError:
        return False
    for token in _NUMBER_TOKEN.findall(source):
        try:
            if normalize_source_number(token) == expected:
                return True
        except ValueError:
            pass
    return False


def _exact_source_line(source_name: str, raw_value: str, source: str) -> str | None:
    """Recover evidence from Markdown itself; never trust model punctuation/HTML."""
    for line in source.splitlines():
        if source_name in line and _source_contains_number(raw_value, line):
            return line.strip()
    return None


def validate_extracted_statement(payload: dict, source_markdown: str, *, extra_concepts=()) -> dict:
    try:
        statement_type = payload["statement_type"]
        entity = str(payload["entity"]).strip()
        scope = payload["scope"]
        period = str(payload["period"]).strip()
        currency = payload.get("currency", "CNY")
        raw_unit = str(payload["raw_unit"]).strip()
        items = payload["items"]
        if statement_type not in STATEMENT_TYPES or not entity or scope not in SCOPES or currency != "CNY" or not isinstance(items, list):
            raise ValueError
        if any(not isinstance(item,dict) or item.get("concept") not in FINANCIAL_CONCEPTS | set(extra_concepts) for item in items):
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid_financial_statement") from exc

    period_info = normalize_period(period, statement_type)
    scale = UNIT_SCALES.get(raw_unit)
    issues: list[str] = []
    if scope == "unknown": issues.append("scope_unknown")
    if period_info is None: issues.append("period_unknown")
    if scale is None: issues.append("unit_unknown")
    values_by_concept: dict[str, set[Decimal]] = {}
    for item in items:
        try:
            values_by_concept.setdefault(item["concept"], set()).add(normalize_source_number(str(item["raw_value"])))
        except (KeyError, ValueError):
            pass
    conflicts = {concept for concept, values in values_by_concept.items() if len(values) > 1}
    issues.extend(f"multiple_values_for_concept:{concept}" for concept in sorted(conflicts))

    validated = []
    for item in items:
        try:
            concept = item["concept"]
            source_name = str(item["source_name"]).strip()
            raw_value = str(item["raw_value"]).strip()
            source_text = str(item["source_text"]).strip()
            number = normalize_source_number(raw_value)
            if not source_name or not source_text:
                raise ValueError
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("invalid_financial_statement") from exc
        exact_line = _exact_source_line(source_name, raw_value, source_markdown)
        found = source_text in source_markdown and _source_contains_number(raw_value, source_text)
        if not found and exact_line:
            source_text, found = exact_line, True
        if not found:
            status, normalized = "source_value_not_found", None
        elif concept in conflicts or scope == "unknown" or period_info is None or scale is None:
            status = "pending_confirmation"
            normalized = _decimal_text(number * scale) if scale is not None else None
        else:
            status, normalized = "source_verified", _decimal_text(number * scale)
        validated.append({
            "concept": concept, "source_name": source_name, "raw_value": raw_value,
            "raw_unit": raw_unit, "normalized_value": normalized,
            "source_text": source_text, "status": status,
        })
    return {
        "statement_type": statement_type, "entity": entity, "scope": scope,
        "period": period, "period_normalized": period_info[0] if period_info else None,
        "period_kind": period_info[1] if period_info else None, "currency": currency,
        "raw_unit": raw_unit, "unit_scale": _decimal_text(scale) if scale is not None else None,
        "issues": issues, "items": validated,
    }
