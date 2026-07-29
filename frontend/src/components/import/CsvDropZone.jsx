/**
 * CsvDropZone — accessible drag-and-drop and click-to-browse CSV upload area.
 *
 * Props
 * ─────
 * onFile     (File) => void   called when a valid file is chosen
 * disabled   boolean          prevents interaction during upload
 * maxSizeMB  number           client-side size limit (default 5)
 * file       File | null      currently selected file (for display)
 * error      string | null    inline validation error to show
 */
import { useCallback, useRef, useState } from 'react'

const MAX_SIZE_DEFAULT = 5

export default function CsvDropZone({
  onFile,
  disabled = false,
  maxSizeMB = MAX_SIZE_DEFAULT,
  file = null,
  error = null,
}) {
  const inputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)

  const validate = useCallback(
    (f) => {
      if (!f) return 'No file selected.'
      if (f.size === 0) return 'The selected file is empty.'
      const ext = f.name.split('.').pop().toLowerCase()
      if (!['csv', 'txt'].includes(ext))
        return `Only .csv and .txt files are accepted (got .${ext}).`
      if (f.size > maxSizeMB * 1024 * 1024)
        return `File exceeds the ${maxSizeMB} MB size limit (${(f.size / 1024 / 1024).toFixed(1)} MB).`
      return null
    },
    [maxSizeMB],
  )

  const handleFile = useCallback(
    (f) => {
      const msg = validate(f)
      if (msg) {
        onFile(null, msg)
      } else {
        onFile(f, null)
      }
    },
    [onFile, validate],
  )

  const handleInputChange = (e) => {
    const f = e.target.files?.[0] ?? null
    handleFile(f)
    // Reset the input value so the same file can be re-selected after an error
    e.target.value = ''
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    const f = e.dataTransfer.files?.[0] ?? null
    handleFile(f)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    if (!disabled) setDragOver(true)
  }

  const handleDragLeave = () => setDragOver(false)

  const handleKeyDown = (e) => {
    if (disabled) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      inputRef.current?.click()
    }
  }

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Drop zone */}
      <div
        role="region"
        aria-label="CSV file upload area"
        aria-describedby={error ? 'dropzone-error' : undefined}
        tabIndex={disabled ? -1 : 0}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onKeyDown={handleKeyDown}
        onClick={() => !disabled && inputRef.current?.click()}
        className={[
          'relative flex flex-col items-center justify-center gap-3',
          'rounded-xl border-2 border-dashed',
          'p-8 sm:p-12',
          'cursor-pointer select-none',
          'transition-colors duration-150',
          'focus-visible:outline-none focus-visible:ring-2',
          'focus-visible:ring-[var(--sf-focus-ring)] focus-visible:ring-offset-2',
          'focus-visible:ring-offset-[var(--sf-bg)]',
          disabled
            ? 'opacity-40 cursor-not-allowed border-[var(--sf-border)]'
            : dragOver
            ? 'border-indigo-400 bg-indigo-500/8'
            : error
            ? 'border-rose-500/50 bg-rose-500/5'
            : file
            ? 'border-emerald-500/40 bg-emerald-500/5'
            : 'border-[var(--sf-border)] hover:border-[var(--sf-border-hover)] hover:bg-white/5',
        ].join(' ')}
      >
        {/* Icon */}
        <svg
          aria-hidden="true"
          className={`w-10 h-10 ${file ? 'text-emerald-400' : 'text-[var(--sf-text-subtle)]'}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          {file ? (
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          ) : (
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
            />
          )}
        </svg>

        {/* Text */}
        {file ? (
          <div className="text-center">
            <p className="text-sm font-medium text-emerald-400 truncate max-w-xs">
              {file.name}
            </p>
            <p className="text-xs text-[var(--sf-text-muted)] mt-0.5">
              {formatSize(file.size)}
            </p>
            {!disabled && (
              <p className="text-xs text-[var(--sf-text-subtle)] mt-1">
                Click or drop to replace
              </p>
            )}
          </div>
        ) : (
          <div className="text-center">
            <p className="text-sm font-medium text-[var(--sf-text)]">
              Drop a CSV file here, or{' '}
              <span className="text-indigo-400 underline underline-offset-2">
                click to browse
              </span>
            </p>
            <p className="text-xs text-[var(--sf-text-subtle)] mt-1">
              .csv and .txt files · max {maxSizeMB} MB
            </p>
          </div>
        )}
      </div>

      {/* Inline error */}
      {error && (
        <p
          id="dropzone-error"
          role="alert"
          className="text-xs text-rose-400 flex items-center gap-1.5"
        >
          <svg aria-hidden="true" className="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
          </svg>
          {error}
        </p>
      )}

      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.txt"
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
        onChange={handleInputChange}
        disabled={disabled}
      />
    </div>
  )
}
