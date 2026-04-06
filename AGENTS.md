# JupyterLab Backend Notes

This backend is being built as a sequential pipeline. The `--mode` flag in
[`src/main.py`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/src/main.py)
means "run up to this stage", not "run only this stage in isolation".

Current intended stage order:

1. `input`
2. `format`
3. `infer_type`
4. `infer_structure`
5. `compute_temporal_stats`
6. `integrity`
7. `audit_missingness`
8. `handle_missingness`
9. `standardize`
10. `univariate_metrics_plotting`
11. `test_transforms`

## Package Layout

- Backend runtime code now lives under [`src/`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/src).
- Ingestion stages live under [`src/ingest/`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/src/ingest).
- Configuration lives under [`src/config/`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/src/config).
- Shared deterministic helpers live under [`src/tools/`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/src/tools).

## Schema / Series Structure

- The time column is derived by the formatter stage. It should not be manually
  overridden from the CLI.
- Entity identifiers are also intended to be derived, not passed in manually.
- In `infer_type.py`, secondary/entity keys should be modeled as
  `secondary_keys: list[str]`, not a single string, because real datasets may
  require a composite entity key such as `(store_id, sku_id)`.
- A dataset with entity identifiers should generally be classified as
  `"multiple"` even if it also has several numeric value columns.
- `infer_type` is deterministic-first. It uses helper functions in
  `src/tools/input_tools.py` and only uses fuzzy/agentic fallback for
  ambiguous secondary-key cases.
- If timestamps are mostly unique, the pipeline should short-circuit away from
  panel detection and classify the dataset as single-series or multivariate.

## Input / Bad Rows

- `run_input_handler()` detects bad/non-data rows and stores them as
  `bad_rows`.
- `bad_rows` is intended for rows that appear in the loaded dataset and do not
  behave like observations because temporal fields are missing or unparseable.
- Each bad row currently carries:
  - `row_index`
  - `csv_row_number`
  - `temporal_values`
  - `reasons`
  - `raw_row`
  - `fuzzy_descriptor`
- The fuzzy descriptor is intentionally lightweight and can be used downstream
  for later cleanup or reporting.
- The recent confusion around `FREDtest.csv` was interpretive, not a current
  code bug:
  - `row_index` is dataframe row index
  - `csv_row_number` is physical CSV line number
  - the `Transform:` row is a bad data row after the header, not the header
    itself
  - the trailing comma-only row was already being detected

## Integrity Expectations

- Integrity checks depend on inferred schema, so `infer_type` should happen
  before `integrity`.
- The quality-handling stages are intended to run after integrity:
  - `audit_missingness` measures value missingness and timestamp holes
  - `handle_missingness` chooses bounded repair actions from the audit
  - `standardize` optionally applies scale transforms after missingness handling
- The current integrity implementation only supports one entity identifier for
  sanity checks.
- As a temporary bridge, integrity uses the first element of `secondary_keys`
  as `entity_col`.
- This is intentionally temporary. The correct long-term behavior is to support
  composite entity keys directly during duplicate and jump checks.

## Quality Handling Status

- The quality-handling package now exists under
  [`src/quality_handling/`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/src/quality_handling)
  and is wired into [`src/main.py`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/src/main.py)
  via the `audit_missingness`, `handle_missingness`, and `standardize` modes.
- `audit_missingness` is deterministic. It separates:
  - missing values inside observed rows
  - missing timestamps / coverage holes in the expected time grid
- Timestamp holes are currently audited and logged, not repaired.
  - The backend does not currently reindex to an expected grid
  - It does not insert synthetic rows for absent timestamps
  - It does not impute missing timestamps as part of `handle_missingness`
- `handle_missingness` is intended for cell-level missing-value handling only.
  - The LLM chooses among bounded strategies such as `leave_as_nan`,
    `forward_fill`, `interpolate`, `zero_fill`, and `drop_rows`
  - The actual data mutation is deterministic and recorded in traces/artifacts
- `standardize` is optional at the dataset level.
  - The stage first profiles scale/tail behavior deterministically
  - Then an LLM gate decides whether point 9 should run at all for the dataset
  - If the gate says `no`, the stage returns the handled dataset unchanged
  - If the gate says `yes`, the LLM may still choose `none` for individual
    columns
- The intended current behavior for SCADA / sensor-style datasets is usually:
  - audit missingness
  - optionally handle cell-level missing values
  - skip standardization unless there is a strong modeling-oriented reason
- The user-facing plan summaries for `handle_missingness` and `standardize`
  are synthesized from the final normalized action list, so they should match
  the actual applied plan rather than raw LLM prose.

## Univariate Analysis Status

- The univariate-analysis package now exists under
  [`src/univariate_analysis/`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/src/univariate_analysis)
  and is wired into [`src/main.py`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/src/main.py)
  via the `univariate_metrics_plotting` and `test_transforms` modes.
- `univariate_metrics_plotting` covers EDA rules 10 and 11.
  - It computes deterministic univariate summary metrics for numeric features
  - It writes per-feature histogram + ECDF plots
  - KDE is only plotted when there is enough continuous support for a stable
    deterministic Gaussian-kernel estimate
  - The stage analyzes the handled dataset path rather than the standardized
    path, so raw-value interpretability is preserved for univariate EDA
- `test_transforms` covers EDA rule 12.
  - It is fully deterministic
  - It only tests transforms for columns with enough evidence that a transform
    might matter, currently using thresholds on non-null support, skewness, and
    tail ratio
  - Candidate transforms are compared by deterministic shape-improvement scores
    rather than LLM judgment or external fitting libraries
  - The stage reports recommendations; it does not mutate the dataset

## State Shape

- The project is moving toward one consolidated state shared across the
  sequential pipeline.
- Until that is finalized, stage outputs should expose a composite state that
  includes every field that has ever been part of the pipeline state, even if a
  given stage has not populated some of those fields yet.
- For earlier modes such as `infer_type`, later-stage integrity-related fields
  may still be present with default values. That is expected.

## Redundancy / Reporting

- There is known redundancy between `report` and other top-level state fields.
- Short term, carrying redundant fields is acceptable while the consolidated
  state is still being worked out.
- Longer term, internal graph state should likely be normalized, with any
  packaged `report` artifact assembled at stage boundaries or final output.
- Deterministic evidence that was cluttering the state has been moved into
  trace files under [`traces/`](/Users/indro/src/tutorials1/agentic_eda/jupyterlab_extension_backend/traces)
  rather than kept in the main payload.
- Stage-produced dataset artifacts such as handled/standardized CSV outputs are
  also written under that same top-level `traces/` directory.

## CLI / Output Intent

- `src/main.py` should prefer derived schema over manual key arguments.
- The output of a stage should reflect the state accumulated up to that stage.
- In particular, `infer_type` should return the full composite payload, not only
  the narrowed `type`/`primary_key`/`secondary_keys` subset.
