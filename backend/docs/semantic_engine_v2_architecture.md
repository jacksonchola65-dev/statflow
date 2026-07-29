# Semantic Engine v2 — Architecture Baseline

This document records the current v1 semantic execution flow in StatFlow, identifies repeated work and performance hotspots, and proposes a v2 shared-feature architecture (FeatureExtraction + lightweight Contexts + v1-compatible adapters) to meet parity and performance goals. v2 is now the default runtime, with v1 available as a fallback option.

Files inspected (v1):
- app/services/file_inspection_service.py (FileInspectionService.inspect_csv)
- app/semantic/detection_pipeline.py (SemanticDetectionPipeline.run, run_batch)
- app/semantic/detectors/* (ValueSamplingDetector, RegexSemanticDetector, DictionarySemanticDetector, other detectors)
- app/semantic/semantic_profile_builder.py (SemanticProfileBuilder.compose)
- app/semantic/semantic_models.py
- app/semantic/semantic_serialization.py (to_dict, from_dict)
- app/semantic/* detectors and candidate detectors (EntityCandidateDetector, EntityKeyDetector, RelationshipDetector, MeasureDetector, DimensionDetector)
- tests/semantic/* (integration and unit scenarios used for validation)

1) Current v1 flow
-------------------
- CSV inspection entry point: `FileInspectionService.inspect_csv(raw_bytes, filename, content_type, owner_id)` reads bytes, decodes, sniffs dialect, reads headers and up to `MAX_SAMPLE_ROWS` rows, constructs `SourceColumn` objects with `sample_values`, `inferred_type`, `nullable`, `position`.
- Sample preparation: per-column `sample_values` are trimmed, blank cells marked nullable, and `_collect_samples` enforces `MAX_SAMPLE_VALUES`.
- Detector execution order: `ValueSamplingDetector`, `RegexSemanticDetector`, `DictionarySemanticDetector` are instantiated and passed to `SemanticDetectionPipeline(detectors)`. The pipeline runs detectors (formerly per-column; now `run_batch` is available) and collects `DetectorResult`s.
- Classification merging: `ConsensusEngine.merge(results)` consolidates detector `DetectorResult`s into ordered `SemanticClassification` outputs per column.
- Domain / entity / key / relationship / analytics: After classifications, `EntityCandidateDetector.discover`, `EntityKeyDetector.discover`, `RelationshipDetector.discover`, `MeasureDetector.discover`, `DimensionDetector.discover`, `AnalyticsRoleService.compose` create higher-order candidates and analytics role profiles.
- `SemanticProfileBuilder.compose(domain_result, entities, rels, keys, analytics_roles, columns)` composes the `SemanticProfile` (columns, entities, relationships, analytics roles, domain). Builder expects candidate models produced above and column `ColumnClassification`s.
- Response serialization: `semantic_to_dict(profile)` (app/semantic/semantic_serialization.py) is attached to `FileInspectionResponse.semantic_profile` and returned. If any exception occurs, an empty dict is returned (best-effort integration).

2) Current performance problems — repeated operations
--------------------------------------------------
Note: these are observed by static inspection and runtime profiling runs (local benchmarks). Frequency is per-request; many operations repeat per-column.

- String cleaning
  - File: `app/services/file_inspection_service.py` (`inspect_csv`) and many detectors
  - Function: inline loops over `col.sample_values` converting non-strings to strings and `strip()`ing.
  - Repeated work: per-column, per-detector if detectors re-clean inputs.
  - Frequency: O(columns * detectors) per inspection request.
  - v2 replacement: central `FeatureExtractionPipeline.clean_values()` producing `ValueFeatureSet.cleaned_values` once per column.

- Normalization / lowercasing
  - File: detectors (regex_detector, dictionary_detector), detection_pipeline usage
  - Function: `s.strip().lower()` in many places (value-sampling also builds `lowered` lists).
  - Repeated work: repeated per-detector per-column normalization.
  - Frequency: O(columns * detectors * samples)
  - v2 replacement: produce `ValueFeatureSet.lowered_values` and `normal_forms` once.

- Regex matching
  - File: `app/semantic/detectors/regex_detector.py`
  - Function: compiling patterns is cached, but many detectors re-run `re.match`/`search` on each sample.
  - Repeated work: repeated matching on same sample values across detectors or multiple rules.
  - Frequency: O(columns * rules * samples)
  - v2 replacement: precompute `ValueFeatureSet.regex_hits` (rule -> hit indices or boolean) once.

- Dictionary lookup
  - File: `dictionary_detector.py`
  - Function: alias normalization and membership checks for known term dictionaries
  - Repeated work: normalizing both dictionary and candidate values repeatedly; some caching exists but cross-detector reuse is weak.
  - Frequency: O(columns * dict_lookups)
  - v2 replacement: centralized `ValueFeatureSet.normalized_tokens` and `dictionary_index` shared across detectors.

- Primitive type inference
  - File: `value_sampling_detector.py` and `file_inspection_service._infer_column_type`
  - Function: numeric, integer, float parsing and checks, repeated across sampling and detectors
  - Repeated work: parsing the same sample values multiple times.
  - Frequency: O(columns * samples * parsing_ops)
  - v2 replacement: `ValueFeatureSet.parsed_numeric` with caching of parse results and summary stats (median, var, counts).

- Sampling
  - File: `file_inspection_service.py` (`_collect_samples`) and detectors
  - Function: trimming samples and limiting to `MAX_SAMPLE_VALUES`; duplication of sampled lists when copied into DetectorInput objects.
  - Repeated work: sample slicing/copying and tuple/list conversions per detector execution.
  - Frequency: O(columns)
  - v2 replacement: single immutable `ColumnFeatureContext.sample_values` reused for all detectors.

- Allocations (objects & tuples)
  - Files: many detectors and pipeline code create `DetectorInput`, `DetectorResult`, `SemanticEvidence`, and `SemanticClassification` transiently per column/detector.
  - Repeated work: allocation churn increases GC pressure and memory.
  - Frequency: O(columns * detectors).
  - v2 replacement: pass lightweight views/pointers into `ColumnFeatureContext` and use detector adapters that avoid copying value arrays (read-only views/tuples).

- Per-column orchestration
  - File: `detection_pipeline.py`, `file_inspection_service.py`
  - Function: sequential driver logic that calls each detector separately per column (or runs batch but still builds per-column inputs repeatedly prior to optimization)
  - Repeated work: building the same intermediate inputs multiple times.
  - v2 replacement: `FeatureExtractionPipeline` drives detectors via adapter interface and supplies cached `SemanticContext` instances.

3) Proposed v2 component diagram (textual)
-------------------------------------------
- CSV Samples
  -> FeatureExtractionPipeline
     - per-file: FileFeatureContext (global dictionaries, compiled regex cache)
     - per-column: ColumnFeatureContext
        - ValueFeatureSet (cleaned_values, lowered_values, tokens, parsed_numbers, regex_hits, dict_hits, cardinality_stats)
  -> Immutable SemanticContext (collection of ColumnFeatureContext + file-level features)
  -> DetectorAdapters (wrap existing v1 detectors, accept SemanticContext & ColumnFeatureContext)
  -> Candidate detectors (Entity/Key/Relationship) unchanged but fed with `ColumnClassification` from merged adapters
  -> SemanticProfileBuilder (v1 builder reused)

Required components (brief):
- FeatureExtractionPipeline: central orchestrator producing `SemanticContext`.
- ColumnFeatureContext: immutable per-column feature container.
- ValueFeatureSet: extracted per-column features (tokenization, normalized forms, parsed numeric, regex/dictionary match maps).
- SemanticContext: file-scoped immutable view of all columns and shared caches.
- v1-compatible detector adapters: thin wrappers exposing v1 detector semantics but using precomputed features.
- SemanticProfileBuilder: reuse v1 builder for exact parity.

4) Proposed data flow
----------------------
CSV bytes -> `FileInspectionService` sample parsing -> create `ColumnFeatureContext` for each column via `FeatureExtractionPipeline` (cleaning, normalization, tokenization, numeric parsing, regex/dict lookup) -> produce immutable `SemanticContext` -> feed `DetectorAdapter.detect(column_context)` or `detect_batch([column_context...])` -> collect `DetectorResult`s -> `ConsensusEngine.merge` -> candidate detectors (Entity/Key/Relationship) -> `SemanticProfileBuilder.compose` -> `semantic_serialization.to_dict` -> attach to response.

5) Compatibility contract
-------------------------
- v1 remains correctness oracle: the v2 detector adapters must reproduce v1 outputs exactly (type, confidence, evidence, ordering).
- Required invariants:
  - identical classifications (SemanticType and confidence)
  - identical evidence payloads (source, score, human-readable description)
  - identical ordering of classifications for a column
  - identical candidate entity/key/relationship sets and ordering
  - identical serialized `SemanticProfile` bytes/dict
  - no changes to public API or `FileInspectionResponse` schema

6) Module proposal (no moves yet; new code under `app/semantic/v2/`)
----------------------------------------------------------------
- app/semantic/v2/__init__.py
- app/semantic/v2/feature_extraction.py  -- FeatureExtractionPipeline, FileFeatureContext
- app/semantic/v2/column_context.py      -- ColumnFeatureContext, ValueFeatureSet
- app/semantic/v2/detector_adapters.py   -- adapters for v1 detectors (ValueSamplingAdapter, RegexAdapter, DictionaryAdapter)
- app/semantic/v2/regex_index.py         -- compiled pattern cache and match helpers
- app/semantic/v2/dictionary_index.py    -- normalized dictionary index and fast membership
- app/semantic/v2/metrics.py             -- timing & memory measurement hooks
- app/semantic/v2/integration.py         -- thin runtime wiring used by FileInspectionService to optionally enable v2

7) Migration sequence (small incremental milestones)
----------------------------------------------------
1. Add new `app/semantic/v2/` package with immutable data models (`ColumnFeatureContext`, `ValueFeatureSet`).
2. Implement `FeatureExtractionPipeline` producing `ColumnFeatureContext` from `SourceColumn.sample_values` (no replacement of detectors yet). Add unit tests for feature correctness.
3. Implement `detector_adapters.py` for `ValueSamplingDetector` only; run semantic unit tests to ensure parity for that detector.
4. Add `RegexIndex` + `DictionaryIndex` and adapter updates; verify regex/dictionary detector parity via tests.
5. Wire `SemanticDetectionPipeline` to accept adapters and an optional `SemanticContext` path; add integration tests (scenario list from `tests/semantic/test_semantic_profile_integration.py`).
6. Performance validation and micro-optimizations (avoid copies, reuse lists/tuples, precompute stats).
7. Gradual rollout: enable v2 behind a feature flag in `FileInspectionService` and compare outputs in CI; when parity is achieved across suites, switch default.

8) Performance budgets (proposal, derived from measured baseline/integrated runs)
------------------------------------------------------------------
Notes: measured integrated p95 for 100 columns ≈ 82 ms, for 250 ≈ 247 ms, for 500 ≈ 487 ms. v2 target budgets below aim to meet acceptance criteria.
- Feature extraction (per-file + per-column):
  - 100 cols: <= 8 ms
  - 250 cols: <= 20 ms
  - 500 cols: <= 40 ms
- Semantic inference (detectors + merging):
  - 100 cols: <= 30 ms
  - 250 cols: <= 60 ms
  - 500 cols: <= 120 ms
- Profile composition (builder + serialization):
  - <= 5 ms for all sizes
- Total integrated inspection (additional semantic overhead target):
  - 100 cols: p95 < 50 ms
  - 250 cols: p95 < 100 ms
  - 500 cols: p95 < 200 ms
- Memory growth budgets (peak additional memory attributed to semantics):
  - 100 cols: <= 250 KB
  - 250 cols: <= 700 KB
  - 500 cols: <= 1.5 MB

9) Risks
--------
- Output parity risk: reproducing exact `evidence.description` strings and classification ordering is brittle; tests must lock these strings.
- Evidence-order risk: merging order may depend on detector execution ordering; adapters must reproduce detector timings/ordering deterministically.
- Detector coupling: detectors that implicitly re-clean or mutate inputs can bypass context; adapters must isolate and wrap those behaviors.
- Memory duplication: naive FeatureExtraction that retains many intermediate arrays will increase peak memory; pay attention to immutable views and shared buffers.
- Premature abstraction: over-abstracting before verifying parity introduces bug surface; use adapter-first approach.
- Benchmark instability: microbenchmarks vary by environment — CI vs developer machines; define reproducible harness and warm-up protocols.

Validation notes / verification
-----------------------------
- Confirmed v1 classes/functions exist by direct inspection of codebase used in the integration: `FileInspectionService.inspect_csv`, `SemanticDetectionPipeline.run_batch`, `ValueSamplingDetector`, `RegexSemanticDetector`, `DictionarySemanticDetector`, `SemanticProfileBuilder.compose`, `semantic_serialization.to_dict/from_dict`, `EntityCandidateDetector`, `EntityKeyDetector`, `RelationshipDetector`, `AnalyticsRoleService`.
- No code changes were made to v1 files in this document.

References to tests used to validate behavior: `tests/semantic/test_semantic_profile_integration.py`, `tests/semantic/*` (entity discovery, domain detection, detection pipeline), and ingestion/inspection tests used during earlier validation.

Appendix: quick example of `ColumnFeatureContext` contents
--------------------------------------------------------
- column_name: str
- sample_values: tuple[str,...] (original trimmed samples)
- cleaned_values: tuple[str,...] (trimmed and normalized)
- lowered_values: tuple[str,...]
- tokens: tuple[tuple[str,...], ...] (tokenized forms per value)
- parsed_numbers: tuple[Optional[float], ...]
- regex_hits: dict[pattern_id -> bitset or list[int]]
- dict_hits: dict[dict_id -> bitset or list[int]]
- stats: {unique_count, cardinality_ratio, null_ratio, median, variance}

---
Document created as a baseline for implementing v2 shared-feature architecture.
