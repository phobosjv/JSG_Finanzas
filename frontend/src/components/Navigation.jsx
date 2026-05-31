import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useAppConfig } from '../context/AppContext'
import { version } from '../../package.json'
import './Navigation.css'

const NAV_LINKS = [
  { to: '/',           key: 'nav.dashboard', icon: '◈' },
  { to: '/markets',    key: 'nav.markets',   icon: '↗' },
  { to: '/portfolio',  key: 'nav.portfolio', icon: '◉' },
  { to: '/tax',        key: 'nav.tax',       icon: '§' },
  { to: '/utilities',  key: 'nav.utilities', icon: '⚙' },
]

export default function Navigation() {
  const { user, logout } = useAuth()
  const { appName, logoUrl, theme, toggleTheme, t } = useAppConfig()

  return (
    <>
      {/* Cabecera superior — móvil */}
      <header className="mobile-header">
        <span className="mobile-header-brand">
          {logoUrl && <img className="mobile-header-logo" src={logoUrl} alt={appName} />}
          <span className="mobile-header-name">{appName}</span>
        </span>
        <span className="mobile-header-version">v{version}</span>
      </header>

      {/* Barra lateral — escritorio */}
      <nav className="sidebar">
        <div className="sidebar-brand">
          {logoUrl && <img className="sidebar-logo" src={logoUrl} alt={appName} />}
          {appName}
          <span className="sidebar-version">v{version}</span>
        </div>
        <div className="sidebar-links">
          {NAV_LINKS.map(l => (
            <NavLink key={l.to} to={l.to} end={l.to === '/'} className={({ isActive }) => isActive ? 'active' : ''}>
              <span className="nav-icon">{l.icon}</span>
              {t(l.key)}
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
                title={theme === 'dark' ? t('utilities.theme_toggle_light') : t('utilities.theme_toggle_dark')}
                style={{ fontSize: '1rem', padding: '4px 8px' }}
              >
                {theme === 'dark' ? '☀' : '◑'}
              </button>
              <button className="btn-ghost btn-sm" onClick={logout}>{t('nav.logout')}</button>
            </div>
          </div>
        )}
      </nav>

      {/* Barra inferior — móvil */}
      <nav className="bottom-nav">
        {NAV_LINKS.map(l => (
          <NavLink key={l.to} to={l.to} end={l.to === '/'} className={({ isActive }) => isActive ? 'active' : ''}>
            <span className="nav-icon">{l.icon}</span>
            <span className="nav-label">{t(l.key)}</span>
          </NavLink>
        ))}
      </nav>
    </>
  )
}
