import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
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

  return (
    <>
      {/* Barra lateral — escritorio */}
      <nav className="sidebar">
        <div className="sidebar-brand">
          FJS Finanzas
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
            <button className="btn-ghost btn-sm" onClick={logout}>Salir</button>
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
