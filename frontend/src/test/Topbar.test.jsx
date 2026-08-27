import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Topbar from '../components/layout/Topbar'

const authState = {
  user: { email: 'admin@example.com', full_name: 'Admin User', role: 'ADMIN' },
  isAuthenticated: true,
  logout: vi.fn(),
}

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => authState,
}))

function renderTopbar(initialEntry = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Topbar />
    </MemoryRouter>,
  )
}

describe('Topbar responsive navigation', () => {
  beforeEach(() => {
    authState.user = { email: 'admin@example.com', full_name: 'Admin User', role: 'ADMIN' }
    authState.isAuthenticated = true
    vi.clearAllMocks()
  })

  it('keeps every admin destination in desktop and mobile navigation', async () => {
    const user = userEvent.setup()
    renderTopbar()

    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Analytics' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Decisions' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Import Data' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'User Management' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Open main navigation' }))
    const mobileNavigation = screen.getByRole('navigation', { name: 'Mobile main navigation links' })
    expect(mobileNavigation).toBeInTheDocument()
    expect(within(mobileNavigation).getAllByRole('link')).toHaveLength(5)
    expect(within(mobileNavigation).getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page')
  })

  it('closes with the close button, Escape, and route selection', async () => {
    const user = userEvent.setup()
    renderTopbar()

    await user.click(screen.getByRole('button', { name: 'Open main navigation' }))
    expect(screen.getByRole('complementary', { name: 'Mobile main navigation' })).toBeInTheDocument()

    const mobileNavigation = screen.getByRole('navigation', { name: 'Mobile main navigation links' })
    await user.click(within(mobileNavigation).getByRole('link', { name: 'Decisions' }))
    expect(screen.queryByRole('complementary', { name: 'Mobile main navigation' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Open main navigation' }))
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('complementary', { name: 'Mobile main navigation' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open main navigation' })).toHaveFocus()
  })

  it('hides restricted destinations for a viewer', async () => {
    const user = userEvent.setup()
    authState.user = { email: 'viewer@example.com', role: 'VIEWER' }
    renderTopbar()

    await user.click(screen.getByRole('button', { name: 'Open main navigation' }))
    const mobileNavigation = screen.getByRole('navigation', { name: 'Mobile main navigation links' })
    expect(within(mobileNavigation).queryByRole('link', { name: 'Import Data' })).not.toBeInTheDocument()
    expect(within(mobileNavigation).queryByRole('link', { name: 'User Management' })).not.toBeInTheDocument()
    expect(within(mobileNavigation).getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
  })
})
