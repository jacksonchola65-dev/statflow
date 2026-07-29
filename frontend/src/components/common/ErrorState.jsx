/**
 * @param {{ message: string, onRetry?: () => void, retrying?: boolean }} props
 */
export default function ErrorState({ message, onRetry, retrying = false }) {
  return (
    <div
      role="alert"
      className="rounded-lg bg-red-900/30 border border-red-500/40 px-4 py-3 text-red-300 text-sm mb-6 flex items-center justify-between gap-4"
    >
      <span>⚠ {message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          className="shrink-0 rounded-md bg-red-500/20 border border-red-500/40 px-3 py-1.5
                     text-xs font-semibold text-red-200 hover:bg-red-500/30
                     disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {retrying ? 'Retrying…' : 'Retry'}
        </button>
      )}
    </div>
  )
}
