import { Component } from 'react'
import { captureExceptionOnce } from '../../services/errorTracking'

export default class AppErrorBoundary extends Component {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error) {
    captureExceptionOnce(error)
  }

  handleRetry = () => {
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <main role="alert" aria-live="assertive" className="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-white">
        <section className="max-w-md space-y-4 text-center">
          <h1 className="text-2xl font-semibold">Something went wrong</h1>
          <p className="text-sm text-slate-300">The application could not render this page.</p>
          <button type="button" onClick={this.handleRetry} className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-400">
            Reload application
          </button>
        </section>
      </main>
    )
  }
}
