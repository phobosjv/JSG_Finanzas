import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Navigation from './components/Navigation'
import ErrorBoundary from './components/ErrorBoundary'
import Login          from './pages/Login'
import Dashboard      from './pages/Dashboard'
import Markets        from './pages/Markets'
import Portfolio      from './pages/Portfolio'
import SecurityDetail from './pages/SecurityDetail'
import TaxReport      from './pages/TaxReport'
import Utilities      from './pages/Utilities'
import AdminPanel     from './pages/AdminPanel'

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="state-loading" style={{ minHeight: '100vh' }}><div className="spinner" /></div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const { user, loading } = useAuth()

  if (loading) return <div className="state-loading" style={{ minHeight: '100vh' }}><div className="spinner" /></div>

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  // Administradores ven solo el panel de administración
  if (user.is_admin) {
    return (
      <ErrorBoundary>
        <Routes>
          <Route path="*" element={<AdminPanel />} />
        </Routes>
      </ErrorBoundary>
    )
  }

  return (
    <div className="layout">
      <Navigation />
      <main className="main-content">
        {/* ErrorBoundary alrededor del contenido: un error de runtime en una
            página muestra un mensaje recuperable en vez de pantalla en negro,
            y el menú lateral sigue funcionando. */}
        <ErrorBoundary>
          <Routes>
            <Route path="/"                  element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/markets"           element={<ProtectedRoute><Markets /></ProtectedRoute>} />
            <Route path="/portfolio"         element={<ProtectedRoute><Portfolio /></ProtectedRoute>} />
            <Route path="/securities/:id"    element={<ProtectedRoute><SecurityDetail /></ProtectedRoute>} />
            <Route path="/tax"               element={<ProtectedRoute><TaxReport /></ProtectedRoute>} />
            <Route path="/utilities"         element={<ProtectedRoute><Utilities /></ProtectedRoute>} />
            <Route path="*"                  element={<Navigate to="/" replace />} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  )
}
