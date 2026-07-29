import time
import uuid
from app.services.file_inspection_service import FileInspectionService
from app.services import file_inspection_service as fis

# Build 100-column CSV
n = 100
headers = [f"c{i}" for i in range(n)]
rows = []
for r in range(10):
    row = ",".join(str((i + r) % 100) for i in range(n))
    rows.append(row)
content = ",".join(headers) + "\n" + "\n".join(rows) + "\n"
raw_bytes = content.encode()

svc = FileInspectionService()
owner = uuid.UUID(int=0)

# Baseline implementation (bypass semantic integration)
def inspect_csv_baseline(raw_bytes, filename, content_type, owner_id):
    filename = fis._normalize_filename(filename)
    fis._validate_extension(filename)
    fis._validate_mime_type(content_type)
    text = fis._decode_bytes(raw_bytes)
    dialect = fis._detect_dialect(text)
    try:
        reader = __import__('csv').reader(__import__('io').StringIO(text), dialect=dialect)
        headers = next(reader)
    except StopIteration:
        raise fis.EmptyFileError("CSV file has no header row.")
    except Exception as exc:
        raise
    if len(headers) > fis.MAX_COLUMNS:
        raise fis.MalformedCsvError("too many columns")
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
    columns = []
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
    # return FileInspectionResponse-like dict without running semantics
    return {
        'inspection_token': token,
        'filename': filename,
        'source_format': 'csv',
        'headers': headers_list,
        'columns': columns,
        'direct_schema_match': direct_schema_match,
        'suggested_mappings': suggested_mappings,
        'warnings': warnings,
        'semantic_profile': {},
    }

# Benchmark helper

def benchmark(fn, warmup=5, runs=20):
    for _ in range(warmup):
        fn(raw_bytes, 'test.csv', 'text/csv', owner)
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn(raw_bytes, 'test.csv', 'text/csv', owner)
        t1 = time.perf_counter()
        times.append(t1 - t0)
    avg = sum(times) / len(times)
    return avg, times

# Run baseline
print('Running baseline (no semantic integration)')
baseline_avg, baseline_times = benchmark(inspect_csv_baseline)
print(f'Baseline average seconds: {baseline_avg:.8f}')
print(f'Baseline average ms: {baseline_avg*1000:.8f}')

# Run integrated
print('Running integrated (with semantic integration)')
integrated_avg, integrated_times = benchmark(svc.inspect_csv)
print(f'Integrated average seconds: {integrated_avg:.8f}')
print(f'Integrated average ms: {integrated_avg*1000:.8f}')

# Compute overhead
additional = integrated_avg - baseline_avg
print(f'Additional overhead seconds: {additional:.8f}')
print(f'Additional overhead ms: {additional*1000:.8f}')

# Print simple validation checks
resp = svc.inspect_csv(raw_bytes, 'test.csv', 'text/csv', owner)
print('SemanticProfile present (non-empty dict)?', bool(resp.semantic_profile))
