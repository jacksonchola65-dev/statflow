/**
 * MappingEditor — column mapping UI for arbitrary CSV files.
 *
 * Props
 * ─────
 * inspection  object   FileInspectionResponse from the backend
 * mappings    array    current mapping state (array of mapping objects)
 * onChange    fn       called with the updated mappings array
 * error       string   top-level validation / backend error to display
 * loading     boolean  disables Generate Preview while in-flight
 * onPreview   fn       called when user clicks Generate Preview
 * onReset     fn       called when user clicks Reset Mappings
 * onBack      fn       called when user clicks Back to file selection
 */
import { useCallback } from 'react'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const TARGET_FIELDS = [
  { key: 'province_code',   label: 'Province',        required: true  },
  { key: 'indicator_code',  label: 'Indicator',       required: true  },
  { key: 'value',           label: 'Value',           required: true  },
  { key: 'reference_year',  label: 'Reference Year',  required: true  },
  { key: 'dataset_name',    label: 'Dataset Name',    required: true  },
  { key: 'source_name',     label: 'Source Name',     required: false },
]

export const TRANSFORMATIONS = [
  { key: 'trim',                  label: 'Trim whitespace'       },
  { key: 'uppercase',             label: 'Uppercase'             },
  { key: 'lowercase',             label: 'Lowercase'             },
  { key: 'parse_number',          label: 'Parse number'          },
  { key: 'extract_year',          label: 'Extract year'          },
  { key: 'province_name_to_code', label: 'Province name → code'  },
]

// ---------------------------------------------------------------------------
// Initial empty mapping for one target field
// ---------------------------------------------------------------------------

export function emptyMapping(targetField) {
  return {
    target_field:  targetField,
    source_type:   'column',      // 'column' | 'fixed_value'
    source_column: '',
    fixed_value:   '',
    transformations: [],
    required: TARGET_FIELDS.find(f => f.key === targetField)?.required ?? true,
  }
}

// ---------------------------------------------------------------------------
// Build the mapping_config payload for the API
// ---------------------------------------------------------------------------

export function buildMappingConfig(mappings) {
  return {
    mapping_version: 1,
    mappings: mappings
      .filter(m => m.source_type === 'fixed_value' ? m.fixed_value.trim() : m.source_column.trim())
      .map(m => ({
        target_field:   m.target_field,
        source_type:    m.source_type,
        source_column:  m.source_type === 'column' ? m.source_column : null,
        fixed_value:    m.source_type === 'fixed_value' ? m.fixed_value : null,
        transformations: m.transformations.map(op => ({ operation: op })),
        required:        m.required,
      })),
  }
}

// ---------------------------------------------------------------------------
// Client-side validation
// ---------------------------------------------------------------------------

/**
 * Returns an object of { [targetFieldKey]: errorString }.
 * Empty means all required fields are valid.
 */
export function validateMappings(mappings) {
  const errors = {}
  const seen = {}

  for (const m of mappings) {
    const field = TARGET_FIELDS.find(f => f.key === m.target_field)
    const hasColumn = !!m.source_column?.trim()
    const hasFixedValue = !!m.fixed_value?.trim()

    if (seen[m.target_field]) {
      errors[m.target_field] = 'Duplicate target field.'
    }
    seen[m.target_field] = true

    if (!field?.required) continue

    if (hasColumn && hasFixedValue) {
      errors[m.target_field] = 'Choose either a source column or a fixed value, not both.'
      continue
    }

    if (m.source_type === 'column' && !hasColumn) {
      errors[m.target_field] = 'Select a source column or switch to Fixed value.'
      continue
    }

    if (m.source_type === 'fixed_value' && !hasFixedValue) {
      errors[m.target_field] = 'Enter a fixed value or switch to Source column.'
    }
  }

  return errors
}

// ---------------------------------------------------------------------------
// Sub-component: one mapping row
// ---------------------------------------------------------------------------

function MappingRow({ mapping, sourceHeaders, onChange, fieldDef }) {
  const handleSourceType = (e) => {
    onChange({ ...mapping, source_type: e.target.value, source_column: '', fixed_value: '' })
  }

  const handleSourceColumn = (e) => {
    onChange({ ...mapping, source_column: e.target.value })
  }

  const handleFixedValue = (e) => {
    onChange({ ...mapping, fixed_value: e.target.value })
  }

  const handleAddTransformation = (e) => {
    const op = e.target.value
    if (!op || mapping.transformations.includes(op)) return
    onChange({ ...mapping, transformations: [...mapping.transformations, op] })
    e.target.value = ''
  }

  const handleRemoveTransformation = (idx) => {
    const next = mapping.transformations.filter((_, i) => i !== idx)
    onChange({ ...mapping, transformations: next })
  }

  const handleMoveTransformation = (idx, direction) => {
    const arr = [...mapping.transformations]
    const to = idx + direction
    if (to < 0 || to >= arr.length) return
    ;[arr[idx], arr[to]] = [arr[to], arr[idx]]
    onChange({ ...mapping, transformations: arr })
  }

  const availableOps = TRANSFORMATIONS.filter(
    t => !mapping.transformations.includes(t.key)
  )

  return (
    <div
      className="rounded-lg border border-[var(--sf-border)] bg-[var(--sf-surface)] p-4 flex flex-col gap-3"
      data-testid={`mapping-row-${mapping.target_field}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-white">
          {fieldDef.label}
        </span>
        {fieldDef.required ? (
          <span className="text-[10px] font-medium uppercase tracking-wide text-rose-400 bg-rose-500/10 rounded px-1.5 py-0.5">
            Required
          </span>
        ) : (
          <span className="text-[10px] font-medium uppercase tracking-wide text-[var(--sf-text-subtle)] bg-slate-700/40 rounded px-1.5 py-0.5">
            Optional
          </span>
        )}
      </div>

      {/* Source type selector */}
      <div className="flex items-center gap-2">
        <label className="text-xs text-[var(--sf-text-muted)] w-24 flex-shrink-0">
          Source type
        </label>
        <select
          value={mapping.source_type}
          onChange={handleSourceType}
          aria-label={`Source type for ${fieldDef.label}`}
          className="flex-1 rounded border border-[var(--sf-border)] bg-slate-800 text-sm text-white px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-400"
        >
          <option value="column">CSV column</option>
          <option value="fixed_value">Fixed value</option>
        </select>
      </div>

      {/* Source column selector */}
      {mapping.source_type === 'column' && (
        <div className="flex items-center gap-2">
          <label className="text-xs text-[var(--sf-text-muted)] w-24 flex-shrink-0">
            Source column
          </label>
          <select
            value={mapping.source_column}
            onChange={handleSourceColumn}
            aria-label={`Source column for ${fieldDef.label}`}
            className="flex-1 rounded border border-[var(--sf-border)] bg-slate-800 text-sm text-white px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-400"
          >
            <option value="">— select column —</option>
            {sourceHeaders.map(h => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        </div>
      )}

      {/* Fixed value input */}
      {mapping.source_type === 'fixed_value' && (
        <div className="flex items-center gap-2">
          <label className="text-xs text-[var(--sf-text-muted)] w-24 flex-shrink-0">
            Fixed value
          </label>
          <input
            type="text"
            value={mapping.fixed_value}
            onChange={handleFixedValue}
            placeholder="Enter fixed value…"
            aria-label={`Fixed value for ${fieldDef.label}`}
            className="flex-1 rounded border border-[var(--sf-border)] bg-slate-800 text-sm text-white px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-400 placeholder:text-slate-500"
          />
        </div>
      )}

      {/* Transformations */}
      <div className="flex flex-col gap-1.5">
        <p className="text-xs text-[var(--sf-text-muted)]">Transformations (applied in order)</p>
        {mapping.transformations.length > 0 && (
          <ol className="flex flex-col gap-1" aria-label={`Transformations for ${fieldDef.label}`}>
            {mapping.transformations.map((op, idx) => {
              const def = TRANSFORMATIONS.find(t => t.key === op)
              return (
                <li key={`${op}-${idx}`} className="flex items-center gap-1.5 text-xs">
                  <span className="flex-1 font-mono text-indigo-300 bg-indigo-900/30 rounded px-2 py-0.5">
                    {def?.label ?? op}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleMoveTransformation(idx, -1)}
                    disabled={idx === 0}
                    aria-label={`Move ${op} up`}
                    className="text-[var(--sf-text-muted)] hover:text-white disabled:opacity-30 disabled:cursor-not-allowed px-1"
                  >↑</button>
                  <button
                    type="button"
                    onClick={() => handleMoveTransformation(idx, 1)}
                    disabled={idx === mapping.transformations.length - 1}
                    aria-label={`Move ${op} down`}
                    className="text-[var(--sf-text-muted)] hover:text-white disabled:opacity-30 disabled:cursor-not-allowed px-1"
                  >↓</button>
                  <button
                    type="button"
                    onClick={() => handleRemoveTransformation(idx)}
                    aria-label={`Remove ${op}`}
                    className="text-rose-400 hover:text-rose-300 px-1"
                  >×</button>
                </li>
              )
            })}
          </ol>
        )}
        {availableOps.length > 0 && (
          <select
            defaultValue=""
            onChange={handleAddTransformation}
            aria-label={`Add transformation for ${fieldDef.label}`}
            className="rounded border border-[var(--sf-border)] bg-slate-800 text-sm text-[var(--sf-text-muted)] px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-400 w-fit"
          >
            <option value="">+ Add transformation</option>
            {availableOps.map(t => (
              <option key={t.key} value={t.key}>{t.label}</option>
            ))}
          </select>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MappingEditor
// ---------------------------------------------------------------------------

export default function MappingEditor({
  inspection,
  mappings,
  onChange,
  error,
  loading = false,
  onPreview,
  onReset,
  onBack,
}) {
  const sourceHeaders = inspection?.headers ?? []
  const fieldErrors = validateMappings(mappings)
  const hasErrors = Object.keys(fieldErrors).length > 0

  const handleMappingChange = useCallback((idx, updated) => {
    const next = mappings.map((m, i) => i === idx ? updated : m)
    onChange(next)
  }, [mappings, onChange])

  const handleGeneratePreview = useCallback(() => {
    if (hasErrors || loading) return
    onPreview(buildMappingConfig(mappings))
  }, [hasErrors, loading, mappings, onPreview])

  return (
    <div className="flex flex-col gap-5 max-w-3xl" aria-label="Column mapping editor">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-white">Map columns</h3>
        <p className="text-sm text-[var(--sf-text-muted)] mt-0.5">
          Map each required target field to a source column or fixed value.
        </p>
      </div>

      {/* Source column list */}
      {sourceHeaders.length > 0 && (
        <div className="rounded-lg border border-[var(--sf-border)] bg-[var(--sf-surface)] px-4 py-3">
          <p className="text-xs font-medium text-[var(--sf-text-muted)] mb-2">
            Detected source columns
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {sourceHeaders.map(h => (
              <li
                key={h}
                className="rounded px-2 py-0.5 bg-indigo-900/40 border border-indigo-500/30 text-indigo-300 text-xs font-mono"
                data-testid="source-column-chip"
              >
                {h}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Backend error banner */}
      {error && (
        <div
          role="alert"
          className="rounded-lg bg-rose-900/30 border border-rose-500/40 px-4 py-3 text-rose-300 text-sm"
          data-testid="mapping-error-banner"
        >
          {error}
        </div>
      )}

      {/* Mapping rows */}
      <div className="flex flex-col gap-3">
        {mappings.map((m, idx) => {
          const fieldDef = TARGET_FIELDS.find(f => f.key === m.target_field) ?? {
            key: m.target_field,
            label: m.target_field,
            required: true,
          }
          return (
            <div key={m.target_field}>
              <MappingRow
                mapping={m}
                sourceHeaders={sourceHeaders}
                fieldDef={fieldDef}
                onChange={(updated) => handleMappingChange(idx, updated)}
              />
              {fieldErrors[m.target_field] && (
                <p className="text-xs text-rose-400 mt-1 px-1" role="alert">
                  {fieldErrors[m.target_field]}
                </p>
              )}
            </div>
          )
        })}
      </div>

      {/* Action row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Generate Preview */}
        <button
          type="button"
          onClick={handleGeneratePreview}
          disabled={hasErrors || loading}
          aria-label="Generate Preview"
          className={[
            'inline-flex items-center justify-center gap-2',
            'rounded-lg px-5 py-2.5 text-sm font-semibold',
            'transition-colors duration-150',
            'focus-visible:outline-none focus-visible:ring-2',
            'focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2',
            'focus-visible:ring-offset-[var(--sf-bg)]',
            hasErrors || loading
              ? 'bg-indigo-600/40 text-white/40 cursor-not-allowed'
              : 'bg-indigo-600 text-white hover:bg-indigo-500',
          ].join(' ')}
          aria-busy={loading}
        >
          {loading ? (
            <>
              <svg aria-hidden="true" className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              Generating…
            </>
          ) : (
            'Generate Preview'
          )}
        </button>

        {/* Reset mappings */}
        <button
          type="button"
          onClick={onReset}
          disabled={loading}
          aria-label="Reset mappings"
          className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-[var(--sf-text-muted)] hover:text-[var(--sf-text)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sf-bg)]"
        >
          Reset mappings
        </button>

        {/* Back to file selection */}
        <button
          type="button"
          onClick={onBack}
          disabled={loading}
          aria-label="Back to file selection"
          className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-[var(--sf-text-muted)] hover:text-[var(--sf-text)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--sf-bg)]"
        >
          ← Back to file selection
        </button>
      </div>
    </div>
  )
}
