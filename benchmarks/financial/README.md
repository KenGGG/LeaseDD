# Financial extraction benchmark

This directory defines benchmark mechanics; it does not claim that a representative benchmark corpus exists. The repository currently has four financial source files from one company. That is insufficient to measure cross-company generalization, and those files must not be described as the proposed 10-company/20-file benchmark.

`manifest.example.json` is intentionally empty. `planned_categories` is a coverage plan, not collected data. Add a file only after its source and human-reviewed expected cell records exist.

## Manifest

Each file entry requires:

- `document_id`: stable benchmark identifier;
- `company_id`: stable company identifier;
- `split`: `dev` or `holdout`;
- `sha256`: lowercase source-file SHA-256;
- `origin`: explicitly `real` or `synthetic`;
- `category`: corpus category, such as `annual_report`.

A company may occur in only one split. Duplicate file hashes are rejected across the whole manifest, including across splits. This prevents the same company or document content leaking from development into holdout.

Validate a manifest with:

```bash
python -m leasedd.extraction_benchmark validate benchmarks/financial/manifest.json
```

## Cell records

Expected and actual JSON files are arrays of normalized per-cell objects. Fields are `document_id`, `company_id`, `table_id`, `statement_type`, `scope`, `period`, `currency`, `unit_scale`, nullable `concept`, `source_name`, `source_row`, `source_column`, nullable string `value`, and `verification_state`. Actual verification state is one of `VERIFIED`, `CONFLICT`, `GAP`, or `UNMAPPED`.

Evaluation matches cells only by the source anchor `(document_id, table_id, source_row, source_column)`. Row and column may be JSON `null` when the source format has no finer locator, but every cell must include both keys and the resulting anchor must be unique. Predicted period, scope, unit, concept, or value never participates in matching, so incorrect semantic metadata cannot be hidden by matching against a different expected cell.

## Metrics

Every metric reports explicit `numerator`, `denominator`, and `value`; a zero denominator yields JSON `null`. Metadata and numeric accuracy also report coverage, and missing predictions or abstentions remain in the accuracy denominator.

- `main_table_discovery`: expected `(document, table, statement type)` tuples found.
- `period_accuracy`, `scope_accuracy`, `unit_accuracy`: correct cells over expected cells. Unit requires both currency and scale.
- `core_concept_recall`: correctly mapped non-null expected concepts over all non-null expected concepts.
- `numeric_accuracy`: source-anchored values with correct period, scope, currency, scale, and Decimal-equivalent value over expected non-null values. This metric isolates numeric transcription and its period/unit basis; it does not certify company, statement type, or concept mapping.
- `false_verified_rate`: incorrect `VERIFIED` cells over all predicted `VERIFIED` cells. An unmatched source anchor or wrong company, statement type, concept, period, scope, currency, scale, or Decimal-equivalent value is false verification. A correct number assigned to the wrong company, statement, or financial concept therefore counts as falsely verified.

Run one split explicitly:

```bash
python -m leasedd.extraction_benchmark evaluate \
  benchmarks/financial/manifest.json expected.json actual.json --split dev
python -m leasedd.extraction_benchmark evaluate \
  benchmarks/financial/manifest.json expected.json actual.json --split holdout
```

Keep holdout labels unavailable during rule and prompt development. The evaluator only reads and scores the requested split; it contains no rule-tuning path. Do not inspect holdout failures to add company-specific rules. Promote failures discovered on development data into general categories such as split tables, multi-level headers, inherited units, mixed scopes, or broken Markdown tables.

Until independent companies and formats have reviewed labels, results demonstrate only evaluator operation and case-level behavior, not a complete real-world extraction benchmark.
