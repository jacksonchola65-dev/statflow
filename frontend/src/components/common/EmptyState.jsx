/**
 * @param {{ message?: string }} props
 */
export default function EmptyState({ message = 'No data available for this selection.' }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-2 text-gray-500">
      <span className="text-3xl" aria-hidden="true">📭</span>
      <p className="text-sm">{message}</p>
    </div>
  )
}
