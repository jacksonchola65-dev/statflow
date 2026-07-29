import Sidebar from './Sidebar'
import Topbar from './Topbar'

/**
 * @param {{ children: React.ReactNode }} props
 */
export default function AppShell({ children }) {
  return (
    <div className="min-h-screen bg-gray-950 text-white flex flex-col">
      <Topbar />
      <div className="flex flex-1">
        <Sidebar />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 max-w-7xl mx-auto w-full">
          {children}
        </main>
      </div>
    </div>
  )
}
