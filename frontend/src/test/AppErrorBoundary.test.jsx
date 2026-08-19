import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AppErrorBoundary from '../components/common/AppErrorBoundary.jsx'

vi.mock('../services/errorTracking.js', () => ({
  captureExceptionOnce: vi.fn(),
}))

function BrokenComponent() {
  throw new Error('secret stack trace')
}

describe('AppErrorBoundary', () => {
  it('renders a safe fallback and exposes a reload action', () => {
    render(
      <AppErrorBoundary>
        <BrokenComponent />
      </AppErrorBoundary>,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
    expect(screen.getByRole('button', { name: 'Reload application' })).toBeInTheDocument()
    expect(screen.queryByText('secret stack trace')).not.toBeInTheDocument()
  })

  it('provides a retry action without exposing the original error', () => {
    render(
      <AppErrorBoundary>
        <BrokenComponent />
      </AppErrorBoundary>,
    )

    const retry = screen.getByRole('button', { name: 'Reload application' })
    expect(retry).toBeEnabled()
    expect(screen.queryByText('secret stack trace')).not.toBeInTheDocument()
  })
})
