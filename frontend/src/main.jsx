import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import 'leaflet/dist/leaflet.css'
import './index.css'
import App from './App.jsx'
import AppErrorBoundary from './components/common/AppErrorBoundary.jsx'
import { AuthProvider } from './contexts/AuthContext.jsx'
import { initializeErrorTracking } from './services/errorTracking.js'

initializeErrorTracking()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AppErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </AppErrorBoundary>
  </StrictMode>,
)
