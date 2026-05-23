import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useAppConfig } from '../context/AppContext'
import { version } from '../../package.json'
import './Navigation.css'

const LINKS = [
  { to: '/',           label: 'Inicio',     icon: '◈' },
  { to: '/markets',    label: 'Mercados',   icon: '↗' },
  { to: '/portfolio',  label: 'Cartera',    icon: '◉' },
  { to: '/tax',        label: 'Fiscal',     icon: '§' },
  { to: '/utilities',  label: 'Utilidades', icon: '⚙' },
]

export default function Navigation() {
  const { user, logout } = useAuth()
  const { appName, theme, toggleTheme } = useAppConfig()

  return (
    <>
      {/* Barra lateral — escritorio */}
      <nav className="sidebar">
        <div className="sidebar-brand">
          {appName}
          <span className="sidebar-version">v{version}</span>
        </div>
        <div className="sidebar-links">
          {LINKS.map(l => (
            <NavLink key={l.to} to={l.to} end={l.to === '/'} className={({ isActive }) => isActive ? 'active' : ''}>
              <span className="nav-icon">{l.icon}</span>
              {l.label}
            </NavLink>
          ))}
        </div>
        {user && (
          <div className="sidebar-footer">
            <span className="text-muted">{user.username}</span>
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <button
                className="btn-ghost btn-sm"
                onClick={toggleTheme}
                title={theme === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
                style={{ fontSize: '1rem', padding: '4px 8px' }}
              >
                {theme === 'dark' ? '☀' : '◑'}
              </button>
              <button className="btn-ghost btn-sm" onClick={logout}>Salir</button>
            </div>
          </div>
        )}
      </nav>

      {/* Barra inferior — móvil */}
      <nav className="bottom-nav">
        {LINKS.map(l => (
          <NavLink key={l.to} to={l.to} end={l.to === '/'} className={({ isActive }) => isActive ? 'active' : ''}>
            <span className="nav-icon">{l.icon}</span>
            <span className="nav-label">{l.label}</span>
          </NavLink>
        ))}
      </nav>
    </>
  )
}
