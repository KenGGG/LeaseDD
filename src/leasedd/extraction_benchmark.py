"""Offline evaluation tools for the financial extraction benchmark.

This module deliberately evaluates predictions; it does not alter extraction rules.
"""
from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


class BenchmarkError(ValueError):
    pass


SPLITS = {"dev", "holdout"}
ORIGINS = {"real", "synthetic"}
STATES = {"VERIFIED", "CONFLICT", "GAP", "UNMAPPED"}
ANCHOR = ("document_id", "table_id", "source_row", "source_column")
RECORD_FIELDS = ("document_id", "company_id", "table_id", "source_row", "source_column",
                 "statement_type", "scope", "period", "currency", "unit_scale", "concept",
                 "source_name", "value", "verification_state")


def validate_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1":
        raise BenchmarkError("manifest schema_version must be '1'")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise BenchmarkError("manifest files must be a list")
    document_ids: set[str] = set()
    hashes: set[str] = set()
    company_splits: dict[str, set[str]] = {}
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise BenchmarkError(f"files[{index}] must be an object")
        for field in ("document_id", "company_id", "split", "sha256", "origin", "category"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise BenchmarkError(f"files[{index}].{field} is required")
        if item["split"] not in SPLITS:
            raise BenchmarkError(f"files[{index}].split must be dev or holdout")
        if item["origin"] not in ORIGINS:
            raise BenchmarkError(f"files[{index}].origin must be real or synthetic")
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise BenchmarkError(f"files[{index}].sha256 must be lowercase SHA-256")
        if item["document_id"] in document_ids:
            raise BenchmarkError("document_id values must be unique")
        if item["sha256"] in hashes:
            raise BenchmarkError("sha256 content duplicate is not allowed")
        document_ids.add(item["document_id"])
        hashes.add(item["sha256"])
        company_splits.setdefault(item["company_id"], set()).add(item["split"])
    leaked = sorted(company for company, splits in company_splits.items() if len(splits) > 1)
    if leaked:
        raise BenchmarkError("company appears in both dev and holdout: " + ", ".join(leaked))
    return manifest


def _anchor(record: dict) -> tuple:
    try:
        return tuple(record[field] for field in ANCHOR)
    except KeyError as error:
        raise BenchmarkError(f"record missing anchor field: {error.args[0]}") from error


def _index(records: list[dict], label: str) -> dict[tuple, dict]:
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise BenchmarkError(f"{label} records must be objects")
        for field in RECORD_FIELDS:
            if field not in record:
                raise BenchmarkError(f"{label} record missing field: {field}")
        anchor = _anchor(record)
        if anchor in result:
            raise BenchmarkError(f"duplicate {label} anchor: {anchor}")
        if label == "actual" and record.get("verification_state") not in STATES:
            raise BenchmarkError("actual verification_state is invalid")
        result[anchor] = record
    return result


def _ratio(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _accuracy(expected: list[dict], actual: dict[tuple, dict], fields: tuple[str, ...]) -> dict:
    covered = correct = 0
    for wanted in expected:
        found = actual.get(_anchor(wanted))
        if found is not None and all(found.get(field) is not None for field in fields):
            covered += 1
            if all(found.get(field) == wanted.get(field) for field in fields):
                correct += 1
    result = _ratio(correct, len(expected))
    result.update(coverage_numerator=covered, coverage_denominator=len(expected),
                  coverage=covered / len(expected) if expected else None)
    return result


def _same_number(left: object, right: object) -> bool:
    if left is None or right is None:
        return False
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except InvalidOperation:
        return False


def evaluate(expected: list[dict], actual: list[dict]) -> dict:
    """Score normalized cells, matching solely by immutable source anchors."""
    expected_index = _index(expected, "expected")
    actual_index = _index(actual, "actual")

    expected_tables = {(r["document_id"], r["table_id"], r.get("statement_type")) for r in expected}
    actual_tables = {(r["document_id"], r["table_id"], r.get("statement_type")) for r in actual}
    discovered = len(expected_tables & actual_tables)

    concepts = [r for r in expected if r.get("concept") is not None]
    recalled = sum(1 for r in concepts if (found := actual_index.get(_anchor(r))) is not None
                   and found.get("concept") == r["concept"])

    numeric = [r for r in expected if r.get("value") is not None]
    numeric_covered = sum(1 for r in numeric if (found := actual_index.get(_anchor(r))) is not None
                          and found.get("value") is not None)
    numeric_correct = sum(1 for r in numeric if (found := actual_index.get(_anchor(r))) is not None
                          and all(found.get(field) == r.get(field)
                                  for field in ("period", "scope", "currency", "unit_scale"))
                          and _same_number(found.get("value"), r["value"]))
    numeric_metric = _ratio(numeric_correct, len(numeric))
    numeric_metric.update(coverage_numerator=numeric_covered, coverage_denominator=len(numeric),
                          coverage=numeric_covered / len(numeric) if numeric else None)

    verified = [r for r in actual if r.get("verification_state") == "VERIFIED"]
    false_verified = 0
    for found in verified:
        wanted = expected_index.get(_anchor(found))
        if wanted is None or any(found.get(field) != wanted.get(field)
                                 for field in ("company_id", "statement_type", "concept",
                                               "period", "scope", "currency", "unit_scale")) \
                or not _same_number(found.get("value"), wanted.get("value")):
            false_verified += 1

    return {
        "main_table_discovery": _ratio(discovered, len(expected_tables)),
        "period_accuracy": _accuracy(expected, actual_index, ("period",)),
        "scope_accuracy": _accuracy(expected, actual_index, ("scope",)),
        "unit_accuracy": _accuracy(expected, actual_index, ("currency", "unit_scale")),
        "core_concept_recall": _ratio(recalled, len(concepts)),
        "numeric_accuracy": numeric_metric,
        "false_verified_rate": _ratio(false_verified, len(verified)),
    }


def _load(path: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkError(f"cannot read {path}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and score financial extraction benchmark data")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("manifest")
    score = commands.add_parser("evaluate")
    score.add_argument("manifest"); score.add_argument("expected"); score.add_argument("actual")
    score.add_argument("--split", choices=sorted(SPLITS), required=True)
    args = parser.parse_args(argv)
    manifest = validate_manifest(_load(args.manifest))
    if args.command == "validate":
        print(json.dumps({"valid": True, "files": len(manifest["files"])}, ensure_ascii=False))
        return 0
    permitted = {f["document_id"] for f in manifest["files"] if f["split"] == args.split}
    expected = [r for r in _load(args.expected) if r.get("document_id") in permitted]
    actual = [r for r in _load(args.actual) if r.get("document_id") in permitted]
    result = {"split": args.split, "expected_records": len(expected), "actual_records": len(actual),
              "metrics": evaluate(expected, actual)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
