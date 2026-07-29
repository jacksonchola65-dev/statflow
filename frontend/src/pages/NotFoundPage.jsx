import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white flex flex-col items-center justify-center gap-6 px-6 text-center">
      <span className="text-7xl font-bold text-indigo-400">404</span>
      <h1 className="text-2xl font-semibold text-white">Page not found</h1>
      <p className="text-gray-400 max-w-sm">
        The page you are looking for does not exist or has been moved.
      </p>
      <Link
        to="/"
        className="mt-2 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
      >
        ← Back to home
      </Link>
    </main>
  )
}
