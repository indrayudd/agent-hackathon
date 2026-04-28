# Graph Report - src  (2026-04-27)

## Corpus Check
- 71 files · ~59,421 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 959 nodes · 1495 edges · 34 communities detected
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 245 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Temporal Splitting And Tools|Temporal Splitting And Tools]]
- [[_COMMUNITY_Inspection Code Templates|Inspection Code Templates]]
- [[_COMMUNITY_Temporal Outlier Detection|Temporal Outlier Detection]]
- [[_COMMUNITY_Temporal Stats State|Temporal Stats State]]
- [[_COMMUNITY_Visualization Specs|Visualization Specs]]
- [[_COMMUNITY_LLM Reasoning Settings|LLM Reasoning Settings]]
- [[_COMMUNITY_Main Quality Pipeline|Main Quality Pipeline]]
- [[_COMMUNITY_Pipeline Orchestration|Pipeline Orchestration]]
- [[_COMMUNITY_Causal Graph Discovery|Causal Graph Discovery]]
- [[_COMMUNITY_Hypothesis Generation|Hypothesis Generation]]
- [[_COMMUNITY_Insight Mining|Insight Mining]]
- [[_COMMUNITY_Granger Causality|Granger Causality]]
- [[_COMMUNITY_Notebook Report Cells|Notebook Report Cells]]
- [[_COMMUNITY_File Loading|File Loading]]
- [[_COMMUNITY_Missingness Handling|Missingness Handling]]
- [[_COMMUNITY_Chat Agent|Chat Agent]]
- [[_COMMUNITY_Type And Integrity|Type And Integrity]]
- [[_COMMUNITY_Story Generation|Story Generation]]
- [[_COMMUNITY_Stationarity Testing|Stationarity Testing]]
- [[_COMMUNITY_Version Snapshots|Version Snapshots]]
- [[_COMMUNITY_Baseline Features|Baseline Features]]
- [[_COMMUNITY_Distribution Drift|Distribution Drift]]
- [[_COMMUNITY_Changepoint Detection|Changepoint Detection]]
- [[_COMMUNITY_Panel Comparison|Panel Comparison]]
- [[_COMMUNITY_Insights Package|Insights Package]]
- [[_COMMUNITY_Reporting Package|Reporting Package]]
- [[_COMMUNITY_Tools Package|Tools Package]]
- [[_COMMUNITY_Causal Package|Causal Package]]
- [[_COMMUNITY_Config Package|Config Package]]
- [[_COMMUNITY_Ingest Package|Ingest Package]]
- [[_COMMUNITY_Quality Package|Quality Package]]
- [[_COMMUNITY_Ingestion Placeholder|Ingestion Placeholder]]
- [[_COMMUNITY_Univariate Package|Univariate Package]]
- [[_COMMUNITY_Readiness Package|Readiness Package]]

## God Nodes (most connected - your core abstractions)
1. `load_dataset()` - 45 edges
2. `run_agent()` - 37 edges
3. `write_stage_trace()` - 34 edges
4. `_merge()` - 28 edges
5. `get_chat_model()` - 28 edges
6. `KnowledgeGraph` - 23 edges
7. `build_report_viz_spec()` - 18 edges
8. `write_stage_plot()` - 18 edges
9. `_common_args()` - 17 edges
10. `normalize_plot_artifact()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `_node_input_handler()` --calls--> `run_input_handler()`  [INFERRED]
  pipeline.py → ingest/handle_inputs.py
- `_node_date_formatter()` --calls--> `run_date_formatter()`  [INFERRED]
  pipeline.py → ingest/format_datetime.py
- `_node_infer_type()` --calls--> `run_infer_type()`  [INFERRED]
  pipeline.py → ingest/infer_type.py
- `_node_infer_structure()` --calls--> `run_infer_structure()`  [INFERRED]
  pipeline.py → ingest/infer_structure.py
- `_node_temporal_stats()` --calls--> `run_compute_temporal_stats()`  [INFERRED]
  pipeline.py → ingest/compute_temporal_stats.py

## Communities

### Community 0 - "Temporal Splitting And Tools"
Cohesion: 0.03
Nodes (100): apply_temporal_split(), _parse_and_sort(), Temporal train / validation / test splitting tool.  Import as:  import src.split, Load dataset, parse the time column, and sort chronologically.      :param path:, Apply a chronological train / validation / test split to a time-series dataset., analyze_header(), apply_missingness_actions(), apply_standardization_actions() (+92 more)

### Community 1 - "Inspection Code Templates"
Cohesion: 0.03
Nodes (67): correlation_code(), handle_missing_ffill_code(), handle_missing_interpolate_code(), inspect_describe_code(), inspect_dtypes_code(), inspect_missing_code(), load_dataset_code(), outlier_detection_code() (+59 more)

### Community 2 - "Temporal Outlier Detection"
Cohesion: 0.03
Nodes (64): detect_time_outliers(), _extract_context(), _gather_columns(), Import as:  import src.dynamics.outlier_detection as soutlier, Store arguments for time-aware outlier detection., Merge target and numeric continuous column lists, preserving order and     remov, Extract up to ``_CONTEXT_RADIUS`` values before and after a given index.      :p, Detect temporal outliers in each target / numeric continuous column using     an (+56 more)

### Community 3 - "Temporal Stats State"
Cohesion: 0.04
Nodes (61): call_infer_structure(), CompositeState, compute_temporal_stats(), _parse_args(), Import as:  import src.ingest.compute_temporal_stats as sctstats, Compute deterministic temporal range, coverage, and frequency statistics.      :, Execute temporal statistics end to end.      :param path: dataset path     :retu, Parse command-line arguments.      :return: parsed arguments (+53 more)

### Community 4 - "Visualization Specs"
Cohesion: 0.06
Nodes (63): append_plot_spec(), _axis_scale(), _build_display(), build_report_viz_spec(), _chart_mark(), _chart_orientation(), _coerce_plot_spec(), _compose_plot_specs() (+55 more)

### Community 5 - "LLM Reasoning Settings"
Cohesion: 0.04
Nodes (59): decide_next_step(), interpret_output(), LLM-powered reasoning for the EDA agent., Ask the LLM to summarize what we learned, including any plot images., Ask the LLM what code to write next based on what we just observed.      :param, get_agent_model(), get_chat_model(), get_gate_model() (+51 more)

### Community 6 - "Main Quality Pipeline"
Cohesion: 0.04
Nodes (51): Execute datetime formatter graph and parse the selected time column.      :param, run_date_formatter(), Execute missingness handling end to end.      :param path: dataset path     :ret, run_handle_missingness(), apply_standardization_plan(), _build_standardization_plan_summary(), call_handle_missingness(), _normalize_standardization_plan() (+43 more)

### Community 7 - "Pipeline Orchestration"
Cohesion: 0.08
Nodes (46): build_pipeline(), _common_args(), compile_pipeline(), _insight_causal_gate(), _merge(), _modeling_gate(), _node_audit_missingness(), _node_changepoints() (+38 more)

### Community 8 - "Causal Graph Discovery"
Cohesion: 0.06
Nodes (42): _done(), _extract_edges(), _find_paths_in_pag(), _load_dataset(), _numeric_cols(), Import as:  import src.causal.causal_graph as scausal, Run causal discovery using the FCI algorithm from causal-learn.      Produces a, Load the best-available dataset from state.      :param state: pipeline state (+34 more)

### Community 9 - "Hypothesis Generation"
Cohesion: 0.06
Nodes (38): generate_hypotheses(), Hypothesis, hypothesis_from_user_question(), Hypothesis generator — formulates investigation questions from initial EDA findi, A single investigation hypothesis., Convert a user's chat question into a formal Hypothesis., Use the LLM to generate investigation hypotheses from initial EDA findings., Process-safe subagent worker — runs in a child process, communicates via queues. (+30 more)

### Community 10 - "Insight Mining"
Cohesion: 0.07
Nodes (35): _compute_insight(), _correlation_score(), _dominance_score(), _evenness_score(), _generate_descriptions(), _modified_z_scores(), _outlier_score(), Import as:  import src.insights.insight_miner as sinsight (+27 more)

### Community 11 - "Granger Causality"
Cohesion: 0.06
Nodes (34): Append an edge to the graph., _done(), _numeric_cols(), _parse_frequency_to_periods(), Import as:  import src.causal.granger as sgranger, Return the trace root directory.      :return: trace root path, Append a stage name to the done list.      :param state: pipeline state     :par, Return the union of continuous and count numeric columns.      :param state: pip (+26 more)

### Community 12 - "Notebook Report Cells"
Cohesion: 0.13
Nodes (35): _bullet_list(), _code(), _conclusion_cells(), _header_cells(), _md(), _phase_10_cells(), _phase_1_3_cells(), _phase_4_cells() (+27 more)

### Community 13 - "File Loading"
Cohesion: 0.13
Nodes (26): _detect_encoding(), _has_nested(), _load_csv(), _load_excel(), load_file(), load_file_excel(), _load_json(), _load_log() (+18 more)

### Community 14 - "Missingness Handling"
Cohesion: 0.09
Nodes (23): Execute missingness auditing end to end.      :param path: dataset path     :ret, run_audit_missingness(), apply_missingness_plan(), _build_missingness_plan_summary(), call_audit_missingness(), CompositeState, maybe_reindex_to_regular_grid(), MissingnessDecision (+15 more)

### Community 15 - "Chat Agent"
Cohesion: 0.13
Nodes (15): Get the top N conclusions by confidence for the executive summary., build_chat_agent(), ChatContext, _fallback_respond(), _llm_respond(), _parse_action_response(), Chat agent for interactive EDA follow-up questions., Parse LLM response for structured action blocks. (+7 more)

### Community 16 - "Type And Integrity"
Cohesion: 0.12
Nodes (15): infer_type(), Infer whether the dataset is single-series, panel, or multivariate using     det, call_date_formatter(), call_infer_type(), IntegrityJudgeOutput, IntegrityState, Import as:  import src.ingest.integrity as sinteg, Infer the series structure and derive the temporary entity key.      :param stat (+7 more)

### Community 17 - "Story Generation"
Cohesion: 0.18
Nodes (14): _build_story_prompt(), _collect_plot_paths(), Import as:  import src.reporting.story_generator as rstory, Build a detailed prompt for narrative story generation.      :param state: pipel, Convert a Story model to a Markdown document.      :param story: Story pydantic, Generate a narrative story from the full pipeline state.      :param state: Comp, One section of the narrative story., Full narrative story output. (+6 more)

### Community 18 - "Stationarity Testing"
Cohesion: 0.21
Nodes (12): _adf_test(), _is_non_stationary_both(), _is_stationary(), _kpss_test(), Phase 10 - Stationarity testing (ADF + KPSS) with auto-differencing.  Import as:, Run Augmented Dickey-Fuller test, return stat + p-value., Run KPSS test (level stationarity), return stat + p-value., Consensus rule:     - ADF rejects null (p < 0.05) => evidence of stationarity (+4 more)

### Community 19 - "Version Snapshots"
Cohesion: 0.32
Nodes (11): create_snapshot(), _history_dir(), list_versions(), _load_index(), Version history for notebook + story snapshots., Save current notebook + story as a version snapshot., Return all version snapshots., Auto-snapshot current state, then restore from a previous version. (+3 more)

### Community 20 - "Baseline Features"
Cohesion: 0.24
Nodes (10): _freq_periods_per_day(), _lag_windows(), Phase 10 - Baseline feature engineering (calendar + lags + rolling).  Import as:, Estimate how many observations fall in one day for the given freq., Return lag sizes (in observation steps) for 1-day, 7-day, 14-day., Return rolling window sizes for 7-day and 30-day., Generate calendar, lag, and rolling features for the dataset.      Lag features, _rolling_windows() (+2 more)

### Community 21 - "Distribution Drift"
Cohesion: 0.27
Nodes (9): _chronological_split(), compare_split_distributions(), _compute_psi(), _parse_and_sort(), Distribution-drift detection between chronological splits.  Import as:  import s, Compare feature distributions between chronological train and test splits., Load dataset, parse the time column, and sort chronologically.      :param path:, Split a sorted dataframe into train and test by timestamp quantiles.      :param (+1 more)

### Community 22 - "Changepoint Detection"
Cohesion: 0.29
Nodes (7): _ChangepointArgs, detect_changepoints(), _gather_columns(), Import as:  import src.dynamics.changepoints as schangepoints, Store arguments for changepoint detection., Merge target and numeric continuous column lists, preserving order and     remov, Detect structural changepoints in each target / numeric continuous column     us

### Community 23 - "Panel Comparison"
Cohesion: 0.32
Nodes (7): compare_panel_entities(), _parse_and_sort(), Import as:  import src.multivariate.panel_compare as spanel, Load dataset, parse the time column, and sort by time.      :param path: dataset, Return the top-n entities by row count.      :param df: dataframe     :param ent, Compare panel entities across target and numeric columns.      For each key nume, _top_entities()

### Community 24 - "Insights Package"
Cohesion: 1.0
Nodes (1): Insight discovery package.

### Community 25 - "Reporting Package"
Cohesion: 1.0
Nodes (1): Reporting and story generation package.

### Community 26 - "Tools Package"
Cohesion: 1.0
Nodes (1): Backend tool package.

### Community 27 - "Causal Package"
Cohesion: 1.0
Nodes (1): Causal analysis package.

### Community 28 - "Config Package"
Cohesion: 1.0
Nodes (1): Backend configuration package.

### Community 29 - "Ingest Package"
Cohesion: 1.0
Nodes (1): Ingestion stages for the Jupyter backend.

### Community 30 - "Quality Package"
Cohesion: 1.0
Nodes (1): Quality-handling stages and helpers for the Jupyter backend.

### Community 31 - "Ingestion Placeholder"
Cohesion: 1.0
Nodes (1): Ingestion module — ingestion logic lives in eda_agent.py goal handlers.

### Community 32 - "Univariate Package"
Cohesion: 1.0
Nodes (1): Univariate analysis stages for the Jupyter backend.

### Community 33 - "Readiness Package"
Cohesion: 1.0
Nodes (1): Model readiness package.

## Knowledge Gaps
- **403 isolated node(s):** `Parse CLI arguments.      :return: parsed arguments`, `Execute selected backend stage.      :param args: parsed CLI args     :return: s`, `Data-leakage validation tool.  Import as:  import src.split.leakage_check as sle`, `Compute Pearson correlation, returning None when it cannot be computed.`, `Validate that the dataset is free from common forms of data leakage.      Three` (+398 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Insights Package`** (2 nodes): `__init__.py`, `Insight discovery package.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Reporting Package`** (2 nodes): `__init__.py`, `Reporting and story generation package.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tools Package`** (2 nodes): `__init__.py`, `Backend tool package.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Causal Package`** (2 nodes): `__init__.py`, `Causal analysis package.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Config Package`** (2 nodes): `__init__.py`, `Backend configuration package.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Ingest Package`** (2 nodes): `__init__.py`, `Ingestion stages for the Jupyter backend.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Quality Package`** (2 nodes): `__init__.py`, `Quality-handling stages and helpers for the Jupyter backend.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Ingestion Placeholder`** (2 nodes): `ingestion.py`, `Ingestion module — ingestion logic lives in eda_agent.py goal handlers.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Univariate Package`** (2 nodes): `__init__.py`, `Univariate analysis stages for the Jupyter backend.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Readiness Package`** (2 nodes): `__init__.py`, `Model readiness package.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_chat_model()` connect `LLM Reasoning Settings` to `Inspection Code Templates`, `Temporal Stats State`, `Causal Graph Discovery`, `Hypothesis Generation`, `Insight Mining`, `Chat Agent`, `Story Generation`?**
  _High betweenness centrality (0.254) - this node is a cross-community bridge._
- **Why does `write_stage_trace()` connect `Causal Graph Discovery` to `Temporal Splitting And Tools`, `Temporal Outlier Detection`, `Temporal Stats State`, `Main Quality Pipeline`, `Insight Mining`, `Granger Causality`, `Missingness Handling`, `Type And Integrity`, `Distribution Drift`, `Changepoint Detection`, `Panel Comparison`?**
  _High betweenness centrality (0.245) - this node is a cross-community bridge._
- **Why does `_trace_root()` connect `Causal Graph Discovery` to `Temporal Splitting And Tools`, `Temporal Outlier Detection`, `LLM Reasoning Settings`, `Granger Causality`, `Notebook Report Cells`, `Story Generation`, `Stationarity Testing`, `Baseline Features`?**
  _High betweenness centrality (0.177) - this node is a cross-community bridge._
- **Are the 29 inferred relationships involving `load_dataset()` (e.g. with `validate_no_leakage()` and `_parse_and_sort()`) actually correct?**
  _`load_dataset()` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `run_agent()` (e.g. with `set_llm_seed()` and `AgentState`) actually correct?**
  _`run_agent()` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `write_stage_trace()` (e.g. with `validate_no_leakage()` and `apply_temporal_split()`) actually correct?**
  _`write_stage_trace()` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `get_chat_model()` (e.g. with `_synthesize_meta_descriptions()` and `_generate_descriptions()`) actually correct?**
  _`get_chat_model()` has 24 INFERRED edges - model-reasoned connections that need verification._