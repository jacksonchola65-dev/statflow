export default function LoadingState({ message = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center h-64 gap-3 text-gray-400">
      <span className="h-5 w-5 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />
      {message}
    </div>
  )
}
