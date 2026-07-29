/**
 * ImportPage — CSV upload, inspect, preview, and confirm flow.
 *
 * State machine:
 *   idle              → user selects a file
 *   file_selected     → file selected, ready to upload
 *   inspecting        → inspectFile() in flight
 *   direct_preview    → direct_schema_match=true → importPreview() done → show preview/confirm
 *   mapping_required  → direct_schema_match=false → show column list, await mapping
 *   inspection_failed → inspectFile() threw → show error
 *   success           → importConfirm() done → show success
 *
 * References: REQ-10
 */
import { useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../components/layout/AppShell'
import DropZone from '../components/import/DropZone'
import PreviewSummary from '../components/import/PreviewSummary'
import ValidationErrorTable from '../components/import/ValidationErrorTable'
import SampleRecordsTable from '../components/import/SampleRecordsTable'
import MappingEditor, { TARGET_FIELDS, emptyMapping } from '../components/import/MappingEditor'
import { inspectFile, importPreview, importConfirm, mapPreview } from '../services/api'

// ---------------------------------------------------------------------------
// Small inline helpers
// ---------------------------------------------------------------------------

/** Upload icon (cloud + arrow) */
function IconUpload() {
  return (
    <svg aria-hidden="true" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
    </svg>
  )
}

/** Spinner */
function Spinner() {
  return (
    <svg aria-hidden="true" className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

/** Check-circle icon */
function IconCheckCircle() {
  return (
    <svg aria-hidden="true" className="w-14 h-14 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Error message extractor
// ---------------------------------------------------------------------------

/**
 * Extract a user-readable message from an error, preferring structured
 * backend detail objects over raw axios error messages.
 *
 * For structured errors:  { response.data.detail: { code, message, details } }
 * For string detail:      { response.data.detail: "Some message" }
 * Fallback:               error.message
 */
function extractErrorMessage(error, fallback = 'Upload failed. Please try again.') {
  const detail = error?.response?.data?.detail

  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string' && detail.message.trim()) return detail.message
    return JSON.stringify(detail)
  }

  return error?.message ?? fallback
}

// ---------------------------------------------------------------------------
// ImportPage
// ---------------------------------------------------------------------------

export default function ImportPage() {
  // ── state ──────────────────────────────────────────────────────────────
  /**
   * 'idle' | 'file_selected' | 'inspecting' | 'direct_preview'
   * | 'mapping_required' | 'mapping_editing' | 'inspection_failed' | 'success'
   */
  const [phase, setPhase] = useState('idle')

  // file selection
  const [file, setFile]           = useState(null)
  const [fileError, setFileError] = useState(null)

  // async flags
  const [uploading,  setUploading]  = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [previewing, setPreviewing] = useState(false)

  // inspection result
  const [inspection, setInspection] = useState(null)

  // mapping state
  const [mappings, setMappings] = useState([])
  const [mappingError, setMappingError] = useState(null)

  // preview phase (direct_preview)
  const [preview, setPreview] = useState(null)

  // mapped preview phase
  const [mappedPreview, setMappedPreview] = useState(null)

  // success phase
  const [result, setResult] = useState(null)

  // error banners
  const [uploadError,  setUploadError]  = useState(null)
  const [confirmError, setConfirmError] = useState(null)

  // ── handlers ───────────────────────────────────────────────────────────

  /** Called by DropZone when the user picks a file. */
  const handleFilePicked = useCallback((picked, err) => {
    setFile(picked)
    setFileError(err)
    setUploadError(null)
    // Move to file_selected only when a valid file was picked
    if (picked && !err) {
      setPhase('file_selected')
    } else {
      setPhase('idle')
    }
  }, [])

  /**
   * Upload the selected file:
   * 1. Inspect → decide path
   * 2a. direct_schema_match=true  → importPreview → direct_preview
   * 2b. direct_schema_match=false → mapping_required
   * 3.  Any failure               → inspection_failed
   */
  const handleUpload = useCallback(async () => {
    if (!file || fileError || uploading) return
    setUploading(true)
    setUploadError(null)
    setInspection(null)
    setPreview(null)
    setMappedPreview(null)
    setPhase('inspecting')

    try {
      const inspectionResult = await inspectFile(file)
      setInspection(inspectionResult)

      if (inspectionResult.direct_schema_match) {
        // Canonical schema — proceed to preview
        const previewData = await importPreview(file)
        setPreview(previewData)
        setPhase('direct_preview')
      } else {
        // Non-canonical schema — enter mapping editor
        // Initialise one mapping slot per required + optional target field
        setMappings(TARGET_FIELDS.map(f => emptyMapping(f.key)))
        setMappingError(null)
        setPhase('mapping_required')
      }
    } catch (err) {
      const msg = extractErrorMessage(err)
      setUploadError(msg)
      setPhase('inspection_failed')
    } finally {
      setUploading(false)
    }
  }, [file, fileError, uploading])

  /** Generate a mapped preview by calling mapPreview() with the current mappings. */
  const handleGeneratePreview = useCallback(async (mappingConfig) => {
    if (!inspection?.inspection_token || previewing) return
    setPreviewing(true)
    setMappingError(null)
    setPhase('mapping_editing')
    try {
      const data = await mapPreview(inspection.inspection_token, mappingConfig)
      setMappedPreview(data)
      setPhase('mapped_preview')
    } catch (err) {
      const msg = extractErrorMessage(err, 'Preview failed. Please check your mappings and try again.')
      setMappingError(msg)
      setPhase('mapping_required')
    } finally {
      setPreviewing(false)
    }
  }, [inspection, previewing])

  /** Reset all mapping fields back to empty defaults. */
  const handleResetMappings = useCallback(() => {
    setMappings(TARGET_FIELDS.map(f => emptyMapping(f.key)))
    setMappingError(null)
  }, [])

  /** Confirm the import using the stored preview token. */
  const handleConfirm = useCallback(async () => {
    if (!preview?.preview_token) return
    setConfirming(true)
    setConfirmError(null)
    try {
      const data = await importConfirm(preview.preview_token)
      setResult(data)
      setPhase('success')
    } catch (err) {
      setConfirmError(err?.message ?? 'Confirm failed. Please try again.')
    } finally {
      setConfirming(false)
    }
  }, [preview])

  /** Reset back to idle so the user can upload a different file. */
  const handleReset = useCallback(() => {
    setPhase('idle')
    setFile(null)
    setFileError(null)
    setPreview(null)
    setMappedPreview(null)
    setInspection(null)
    setResult(null)
    setUploadError(null)
    setConfirmError(null)
    setMappings([])
    setMappingError(null)
  }, [])

  /** Return to the mapping editor without re-inspecting the file. */
  const handleBackToMapping = useCallback(() => {
    setMappedPreview(null)
    setPhase('mapping_required')
  }, [])

  // ── render ─────────────────────────────────────────────────────────────

  // Phases that show the file upload form
  const isIdlePhase = phase === 'idle' || phase === 'file_selected' || phase === 'inspecting' || phase === 'inspection_failed'

  return (
    <AppShell>
      {/* ── Page header ── */}
      <div className="mb-6">
        <h2
          className="text-2xl font-bold text-white tracking-tight"
          style={{ fontFamily: 'var(--sf-font-family)' }}
        >
          Import Dataset
        </h2>
        <p className="mt-1 text-sm text-[var(--sf-text-muted)]">
          Upload a CSV file to preview, validate, and import province-level indicator data.
        </p>
      </div>

      {/* ════════════════════ PHASES: IDLE / FILE_SELECTED / INSPECTING / INSPECTION_FAILED ════════════════════ */}
      {isIdlePhase && (
        <div className="max-w-2xl flex flex-col gap-5">
          {/* Drop zone — shows filename once selected */}
          <DropZone
            file={file}
            error={fileError}
            disabled={uploading}
            onFile={handleFilePicked}
          />

          {/* Upload / inspection error banner */}
          {uploadError && (
            <div
              role="alert"
              className="rounded-lg bg-rose-900/30 border border-rose-500/40 px-4 py-3 text-rose-300 text-sm flex items-start gap-2"
            >
              <svg aria-hidden="true" className="w-4 h-4 flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
              </svg>
              <span>{uploadError}</span>
            </div>
          )}

          {/* Upload button */}
          <button
            type="button"
            onClick={handleUpload}
            disabled={!file || !!fileError || uploading}
            className={[
              'inline-flex items-center justify-center gap-2',
              'rounded-lg px-5 py-2.5',
              'text-sm font-semibold',
              'transition-colors duration-150',
              'focus-visible:outline-none focus-visible:ring-2',
              'focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2',
              'focus-visible:ring-offset-[var(--sf-bg)]',
              !file || !!fileError || uploading
                ? 'bg-indigo-600/40 text-white/40 cursor-not-allowed'
                : 'bg-indigo-600 text-white hover:bg-indigo-500 active:bg-indigo-700',
            ].join(' ')}
            aria-busy={uploading}
          >
            {uploading ? (
              <>
                <Spinner />
                Inspecting…
              </>
            ) : (
              <>
                <IconUpload />
                Upload &amp; Preview
              </>
            )}
          </button>
        </div>
      )}

      {/* ════════════════════ PHASE: MAPPING_REQUIRED / MAPPING_EDITING ════════════════════ */}
      {(phase === 'mapping_required' || phase === 'mapping_editing') && inspection && (
        <div className="max-w-3xl flex flex-col gap-3">
          {/* Filename still visible */}
          {file && (
            <p className="text-sm text-[var(--sf-text-muted)]">
              File: <span className="font-medium text-white">{file.name}</span>
            </p>
          )}

          <MappingEditor
            inspection={inspection}
            mappings={mappings}
            onChange={setMappings}
            error={mappingError}
            loading={previewing}
            onPreview={handleGeneratePreview}
            onReset={handleResetMappings}
            onBack={handleReset}
          />
        </div>
      )}

      {/* ════════════════════ PHASE: MAPPED_PREVIEW ════════════════════ */}
      {phase === 'mapped_preview' && mappedPreview && (
        <div className="flex flex-col gap-5 max-w-6xl">
          <div className="rounded-xl border border-[var(--sf-border)] bg-[var(--sf-surface)] p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-white">Mapped preview</h3>
                <p className="text-sm text-[var(--sf-text-muted)] mt-1">
                  File: <span className="font-medium text-white">{file?.name ?? inspection?.filename ?? 'Uploaded file'}</span>
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleBackToMapping}
                  className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-[var(--sf-text-muted)] hover:text-[var(--sf-text)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sf-bg)]"
                >
                  ← Back to Mapping
                </button>
                <button
                  type="button"
                  disabled
                  aria-disabled="true"
                  className="inline-flex items-center justify-center rounded-lg px-5 py-2.5 text-sm font-semibold bg-emerald-600/30 text-emerald-300/40 cursor-not-allowed"
                >
                  Confirm Import
                </button>
              </div>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-4">
            <div className="rounded-lg border border-[var(--sf-border)] bg-[var(--sf-surface)] p-4">
              <p className="text-xs uppercase tracking-wide text-[var(--sf-text-muted)]">Total preview rows</p>
              <p className="mt-2 text-2xl font-semibold text-white">{mappedPreview.total_preview_rows}</p>
            </div>
            <div className="rounded-lg border border-[var(--sf-border)] bg-[var(--sf-surface)] p-4">
              <p className="text-xs uppercase tracking-wide text-[var(--sf-text-muted)]">Mapped columns</p>
              <p className="mt-2 text-2xl font-semibold text-white">{mappedPreview.mapped_column_count}</p>
            </div>
            <div className="rounded-lg border border-[var(--sf-border)] bg-[var(--sf-surface)] p-4 md:col-span-2">
              <p className="text-xs uppercase tracking-wide text-[var(--sf-text-muted)]">Original headers</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {(mappedPreview.original_headers ?? []).map(header => (
                  <span key={header} className="rounded px-2 py-1 bg-indigo-900/40 border border-indigo-500/30 text-indigo-300 text-xs font-mono">
                    {header}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--sf-border)] bg-[var(--sf-surface)] p-4">
            <p className="text-xs uppercase tracking-wide text-[var(--sf-text-muted)]">Target fields</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(mappedPreview.target_fields ?? []).map(field => (
                <span key={field} className="rounded px-2 py-1 bg-slate-800 border border-[var(--sf-border)] text-sm text-white">
                  {field}
                </span>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-[var(--sf-border)] bg-[var(--sf-surface)] p-4">
            <p className="text-sm font-semibold text-white mb-3">Transformed rows</p>
            {mappedPreview.transformed_rows?.length ? (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm text-left">
                  <thead>
                    <tr className="border-b border-[var(--sf-border)] text-[var(--sf-text-muted)]">
                      {(mappedPreview.target_fields ?? []).map(field => (
                        <th key={field} className="px-3 py-2 font-medium">{field}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {mappedPreview.transformed_rows.map((row, idx) => (
                      <tr key={`${row?.[mappedPreview.target_fields?.[0]] ?? 'row'}-${idx}`} className="border-b border-[var(--sf-border)]/60 text-white">
                        {(mappedPreview.target_fields ?? []).map(field => (
                          <td key={field} className="px-3 py-2 align-top">
                            {row?.[field] ?? ''}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-[var(--sf-text-muted)]">No transformed rows to display.</p>
            )}
          </div>
        </div>
      )}

      {/* ════════════════════ PHASE: DIRECT_PREVIEW ════════════════════ */}
      {phase === 'direct_preview' && preview && (
        <div className="flex flex-col gap-5 max-w-4xl">
          {/* Summary badges */}
          <PreviewSummary preview={preview} />

          {/* Validation error table — only when invalid rows exist */}
          {preview.invalid_rows > 0 && (
            <ValidationErrorTable
              errors={preview.errors}
              totalErrorCount={preview.total_error_count}
              errorsTruncated={preview.errors_truncated}
            />
          )}

          {/* Sample records table */}
          <SampleRecordsTable records={preview.sample_records} />

          {/* Confirm error banner */}
          {confirmError && (
            <div
              role="alert"
              className="rounded-lg bg-rose-900/30 border border-rose-500/40 px-4 py-3 text-rose-300 text-sm flex items-start gap-2"
            >
              <svg aria-hidden="true" className="w-4 h-4 flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
              </svg>
              <span>{confirmError}</span>
            </div>
          )}

          {/* Action row */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Confirm Import — only enabled when can_confirm is true */}
            <button
              type="button"
              onClick={handleConfirm}
              disabled={!preview.can_confirm || confirming}
              className={[
                'inline-flex items-center justify-center gap-2',
                'rounded-lg px-5 py-2.5',
                'text-sm font-semibold',
                'transition-colors duration-150',
                'focus-visible:outline-none focus-visible:ring-2',
                'focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2',
                'focus-visible:ring-offset-[var(--sf-bg)]',
                !preview.can_confirm || confirming
                  ? 'bg-emerald-600/30 text-emerald-300/40 cursor-not-allowed'
                  : 'bg-emerald-600 text-white hover:bg-emerald-500 active:bg-emerald-700',
              ].join(' ')}
              aria-disabled={!preview.can_confirm}
              aria-busy={confirming}
            >
              {confirming ? (
                <>
                  <Spinner />
                  Importing…
                </>
              ) : (
                <>
                  <svg aria-hidden="true" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  Confirm Import
                </>
              )}
            </button>

            {/* Upload a different file */}
            <button
              type="button"
              onClick={handleReset}
              disabled={confirming}
              className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-[var(--sf-text-muted)] hover:text-[var(--sf-text)] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sf-bg)] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <svg aria-hidden="true" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
              </svg>
              Upload a different file
            </button>
          </div>
        </div>
      )}

      {/* ════════════════════ PHASE: SUCCESS ════════════════════ */}
      {phase === 'success' && result && (
        <div className="max-w-lg">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-8 flex flex-col items-center text-center gap-5">
            <IconCheckCircle />

            <div>
              <p className="text-2xl font-bold text-white tabular-nums">
                {result.imported_count.toLocaleString()}{' '}
                <span className="text-emerald-400">
                  row{result.imported_count !== 1 ? 's' : ''}
                </span>
              </p>
              <p className="mt-1 text-sm text-[var(--sf-text-muted)]">
                successfully imported into the database.
              </p>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-3 mt-2">
              <Link
                to="/dashboard"
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sf-bg)]"
              >
                <svg aria-hidden="true" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                </svg>
                View Dashboard
              </Link>

              <button
                type="button"
                onClick={handleReset}
                className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-[var(--sf-text-muted)] hover:text-[var(--sf-text)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sf-bg)]"
              >
                Import another file
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  )
}
