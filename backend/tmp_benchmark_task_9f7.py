import csv
import io
import math
import time
import tracemalloc
import uuid
from statistics import mean
from app.services.file_inspection_service import FileInspectionService
from app.services import file_inspection_service as fis
from app.semantic.detection_pipeline import SemanticDetectionPipeline
from app.semantic.detectors.value_sampling_detector import ValueSamplingDetector
from app.semantic.detectors.regex_detector import RegexSemanticDetector
from app.semantic.detectors.dictionary_detector import DictionarySemanticDetector
from app.semantic.detectors.base import DetectorInput
from app.semantic.entity_candidate_detector import EntityColumnInput, EntityCandidateDetector
from app.semantic.entity_key_detector import EntityKeyColumnInput, EntityKeyDetectionInput, EntityKeyDetector
from app.semantic.relationship_detector import RelationshipColumnInput, RelationshipDetectionInput, RelationshipDetector
from app.semantic.measure_detector import MeasureColumnInput, MeasureDetector
from app.semantic.dimension_detector import DimensionColumnInput, DimensionDetector
from app.semantic.analytics_role_service import AnalyticsRoleService
from app.semantic.semantic_profile_builder import SemanticProfileBuilder, DomainDetectionResult, ColumnClassification
from app.semantic.semantic_serialization import to_dict as semantic_to_dict
from app.semantic.semantic_types import DatasetDomain

OWNER = uuid.UUID(int=0)
svc = FileInspectionService()

COLUMN_SIZES = [10, 50, 100, 250, 500]


def make_csv(num_cols: int) -> bytes:
    headers = [f"c{i}" for i in range(num_cols)]
    rows = []
    for r in range(10):
        rows.append(",".join(str((i + r) % 100) for i in range(num_cols)))
    content = ",".join(headers) + "\n" + "\n".join(rows) + "\n"
    return content.encode("utf-8")


def inspect_csv_baseline(raw_bytes, filename, content_type, owner_id):
    filename = fis._normalize_filename(filename)
    fis._validate_extension(filename)
    fis._validate_mime_type(content_type)
    text = fis._decode_bytes(raw_bytes)
    dialect = fis._detect_dialect(text)
    try:
        reader = csv.reader(io.StringIO(text), dialect=dialect)
        headers = next(reader)
    except StopIteration:
        raise fis.EmptyFileError("CSV file has no header row.")
    except csv.Error as exc:
        raise fis.MalformedCsvError(f"CSV parsing failed: {exc}") from exc

    if len(headers) > fis.MAX_COLUMNS:
        raise fis.MalformedCsvError("CSV file contains too many columns.")

    normalized_headers = [fis._normalize_header(h) for h in headers]
    sample_rows = []
    row_count = 0
    for row in reader:
        if len(row) == 0:
            continue
        row_count += 1
        if len(sample_rows) < fis.MAX_SAMPLE_ROWS:
            sample_rows.append(row)
        if row_count >= fis.MAX_SAMPLE_ROWS:
            break

    num_columns = len(normalized_headers)
    column_samples = [[] for _ in range(num_columns)]
    nullable_flags = [False] * num_columns

    for row in sample_rows:
        normalized_row = [cell.strip() for cell in row]
        if len(normalized_row) < num_columns:
            normalized_row += [""] * (num_columns - len(normalized_row))
        for idx in range(num_columns):
            value = normalized_row[idx] if idx < len(normalized_row) else ""
            if value == "":
                nullable_flags[idx] = True
            else:
                column_samples[idx].append(value[:fis.MAX_SAMPLE_VALUE_LENGTH])

    columns = []
    for idx, header in enumerate(headers):
        sample_values = fis._collect_samples(column_samples[idx], fis.MAX_SAMPLE_VALUES)
        inferred_type = fis._infer_column_type([v for v in column_samples[idx]])
        columns.append(fis.SourceColumn(
            name=header.strip(),
            inferred_type=inferred_type,
            sample_values=sample_values,
            nullable=nullable_flags[idx],
            position=idx + 1,
        ))

    headers_list = [header.strip() for header in headers]
    direct_schema_match = fis.CANONICAL_REQUIRED_HEADERS.issubset({h.lower() for h in normalized_headers})
    warnings = []
    suggested_mappings = fis._build_suggested_mappings(headers_list, normalized_headers)
    payload = fis.CachedInspection(
        inspection_token="",
        filename=filename,
        source_format="csv",
        headers=headers_list,
        columns=columns,
        direct_schema_match=direct_schema_match,
        suggested_mappings=suggested_mappings,
        warnings=warnings,
        owner_id=owner_id,
    )
    token = fis._store_inspection_token(payload)
    payload = fis.CachedInspection(
        inspection_token=token,
        filename=filename,
        source_format="csv",
        headers=headers_list,
        columns=columns,
        direct_schema_match=direct_schema_match,
        suggested_mappings=suggested_mappings,
        warnings=warnings,
        owner_id=owner_id,
    )
    fis._INSPECTION_STORE[token] = fis._InspectionTokenEntry(payload=payload)
    return {
        "inspection_token": token,
        "filename": filename,
        "source_format": "csv",
        "headers": headers_list,
        "columns": columns,
        "direct_schema_match": direct_schema_match,
        "suggested_mappings": suggested_mappings,
        "warnings": warnings,
        "semantic_profile": {},
    }


def benchmark(fn, raw_bytes, warmup=5, runs=30):
    for _ in range(warmup):
        fn(raw_bytes, "test.csv", "text/csv", OWNER)
    times = []
    peaks = []
    for _ in range(runs):
        tracemalloc.start()
        t0 = time.perf_counter()
        fn(raw_bytes, "test.csv", "text/csv", OWNER)
        elapsed = time.perf_counter() - t0
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        times.append(elapsed)
        peaks.append(peak)
    times.sort()
    avg = mean(times)
    p95_index = min(len(times) - 1, math.ceil(0.95 * len(times)) - 1)
    return {
        "avg": avg,
        "p95": times[p95_index],
        "min": times[0],
        "max": times[-1],
        "peak_bytes_avg": mean(peaks),
        "peak_bytes_max": max(peaks),
    }


def run_size(size):
    raw = make_csv(size)
    original_max = fis.MAX_COLUMNS
    try:
        fis.MAX_COLUMNS = max(original_max, size)
        baseline = benchmark(inspect_csv_baseline, raw)
        integrated = benchmark(svc.inspect_csv, raw)
    finally:
        fis.MAX_COLUMNS = original_max
    return baseline, integrated


def count_semantic_columns(response):
    return len(response.semantic_profile.get("columns", [])) if isinstance(response.semantic_profile, dict) else 0


def validate_determinism(size):
    raw = make_csv(size)
    original_max = fis.MAX_COLUMNS
    try:
        fis.MAX_COLUMNS = max(original_max, size)
        resp1 = svc.inspect_csv(raw, "test.csv", "text/csv", OWNER)
        resp2 = svc.inspect_csv(raw, "test.csv", "text/csv", OWNER)
    finally:
        fis.MAX_COLUMNS = original_max
    return resp1 == resp2


def compare_single_vs_batch(size):
    headers = [f"c{i}" for i in range(size)]
    columns = []
    for i in range(size):
        values = [str((i + r) % 100) for r in range(10)]
        columns.append(DetectorInput(column_name=headers[i], values=tuple(values), inferred_type=None))
    pipeline = SemanticDetectionPipeline([ValueSamplingDetector(), RegexSemanticDetector(), DictionarySemanticDetector()])
    single = [pipeline.run(inp) for inp in columns]
    batch = pipeline.run_batch(columns)
    return single == batch


def main():
    results = {}
    semantic_counts = {}
    deterministic = True
    for size in COLUMN_SIZES:
        baseline, integrated = run_size(size)
        original_max = fis.MAX_COLUMNS
        try:
            fis.MAX_COLUMNS = max(original_max, size)
            raw = make_csv(size)
            resp = svc.inspect_csv(raw, "test.csv", "text/csv", OWNER)
        finally:
            fis.MAX_COLUMNS = original_max
        semantic_counts[size] = count_semantic_columns(resp)
        deterministic &= validate_determinism(size)
        results[size] = {
            "baseline": baseline,
            "integrated": integrated,
            "overhead": integrated["avg"] - baseline["avg"],
        }
    thresholds = {100: 0.050, 250: 0.100, 500: 0.200}
    passed_thresholds = all(results[size]["integrated"]["p95"] < thresholds[size] for size in thresholds)
    print(f"DETERMINISM={deterministic}")
    print(f"OUTPUT_EQUALITY=UNKNOWN")
    print(f"PASS_THRESHOLD_100MS={results[100]['integrated']['p95'] < thresholds[100]}")
    print(f"PASS_THRESHOLD_250MS={results[250]['integrated']['p95'] < thresholds[250]}")
    print(f"PASS_THRESHOLD_500MS={results[500]['integrated']['p95'] < thresholds[500]}")
    for size, values in results.items():
        print(f"SIZE={size}")
        print(f"BASELINE_AVG_SECONDS={values['baseline']['avg']:.12f}")
        print(f"BASELINE_P95_SECONDS={values['baseline']['p95']:.12f}")
        print(f"BASELINE_MIN_SECONDS={values['baseline']['min']:.12f}")
        print(f"BASELINE_MAX_SECONDS={values['baseline']['max']:.12f}")
        print(f"INTEGRATED_AVG_SECONDS={values['integrated']['avg']:.12f}")
        print(f"INTEGRATED_P95_SECONDS={values['integrated']['p95']:.12f}")
        print(f"INTEGRATED_MIN_SECONDS={values['integrated']['min']:.12f}")
        print(f"INTEGRATED_MAX_SECONDS={values['integrated']['max']:.12f}")
        print(f"OVERHEAD_AVG_SECONDS={values['overhead']:.12f}")
        print(f"BASELINE_PEAK_BYTES_AVG={values['baseline']['peak_bytes_avg']}")
        print(f"INTEGRATED_PEAK_BYTES_AVG={values['integrated']['peak_bytes_avg']}")
        print(f"PEAK_BYTES_OVERHEAD_AVG={values['integrated']['peak_bytes_avg'] - values['baseline']['peak_bytes_avg']}")
        print(f"SEMANTIC_COLUMN_COUNT={semantic_counts[size]}")
    print(f"ALL_THRESHOLD_PASSED={passed_thresholds}")


if __name__ == "__main__":
    main()
