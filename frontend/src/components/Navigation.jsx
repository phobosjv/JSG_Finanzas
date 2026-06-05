import { useState, useEffect, useRef } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useAppConfig } from '../context/AppContext'
import { api } from '../api/client'
import { version } from '../../package.json'
import './Navigation.css'

const NAV_LINKS = [
  { to: '/',           key: 'nav.dashboard', icon: '◈' },
  { to: '/markets',    key: 'nav.markets',   icon: '↗' },
  { to: '/portfolio',  key: 'nav.portfolio', icon: '◉' },
  { to: '/tax',        key: 'nav.tax',       icon: '§' },
  { to: '/utilities',  key: 'nav.utilities', icon: '⚙' },
]

// Alertas de COMPRA: fuente = favorites.target_buy_price + last_price
function computeBuyAlerts(favorites) {
  const result = []
  for (const fav of favorites) {
    const price = fav.last_price != null ? Number(fav.last_price) : null
    const buy = fav.target_buy_price != null ? Number(fav.target_buy_price) : null
    if (price !== null && buy !== null && buy > 0 && price <= buy) {
      result.push({
        security_id: fav.security_id,
        name: fav.name,
        yahoo_ticker: fav.yahoo_ticker,
        alertType: 'buy',
      })
    }
  }
  return result
}

// Alertas de VENTA: fuente = positions.target_sell_price + current_price
function computeSellAlerts(portfolio) {
  const result = []
  for (const pos of portfolio) {
    const price = pos.current_price != null ? Number(pos.current_price) : null
    if (price === null) continue
    const sell = pos.target_sell_price != null ? Number(pos.target_sell_price) : null
    if (sell !== null && sell > 0 && price >= sell) {
      result.push({
        security_id: pos.security_id,
        name: pos.name,
        yahoo_ticker: pos.yahoo_ticker,
        alertType: 'sell',
      })
    }
  }
  return result
}

// Componente campana con popup de alertas.
// placement='up': el popup abre hacia arriba (sidebar-footer).
// placement='down': el popup abre hacia abajo (mobile-header).
function AlertBell({ alerts, t, placement }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const hasAlerts = alerts.length > 0

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        className="btn-ghost btn-sm"
        onClick={() => setOpen(v => !v)}
        title={t('nav.alerts_title')}
        style={{ fontSize: '1rem', padding: '4px 8px', opacity: hasAlerts ? 1 : 0.35 }}
      >
        🔔
        {hasAlerts && (
          <span style={{
            position: 'absolute', top: 1, right: 1,
            background: 'var(--green, #16a34a)', color: '#fff',
            borderRadius: '50%', width: 15, height: 15,
            fontSize: '0.6rem', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 700, lineHeight: 1, pointerEvents: 'none',
          }}>
            {alerts.length > 9 ? '9+' : alerts.length}
          </span>
        )}
      </button>

      {open && (
        <div className={`alert-popup alert-popup-${placement}`}>
          <div className="alert-popup-header">
            <strong>{t('nav.alerts_title')}</strong>
            <button
              className="btn-ghost btn-sm"
              style={{ padding: '1px 6px', fontSize: '0.8rem' }}
              onClick={() => setOpen(false)}
            >✕</button>
          </div>
          {alerts.length === 0 ? (
            <div style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              {t('nav.alerts_empty')}
            </div>
          ) : (
            alerts.map(a => (
              <div
                key={a.security_id}
                className="alert-popup-item"
                onClick={() => { navigate(`/securities/${a.security_id}`); setOpen(false) }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                  <span className="alert-popup-name">{a.name}</span>
                  <span className="alert-popup-ticker">{a.yahoo_ticker}</span>
                </div>
                <span className="alert-popup-badge">
                  {a.alertType === 'sell' ? t('sd.alert_sell') : t('sd.alert_buy')}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export default function Navigation() {
  const { user, logout } = useAuth()
  const { appName, logoUrl, theme, toggleTheme, t } = useAppConfig()
  const [alerts, setAlerts] = useState([])

  useEffect(() => {
    if (!user) return
    let cancelled = false
    async function loadAlerts() {
      try {
        const [portfolio, favorites] = await Promise.all([
          api.get('/portfolio'),
          api.get('/favorites'),
        ])
        if (cancelled) return
        const buyAlerts = computeBuyAlerts(favorites)
        const sellAlerts = computeSellAlerts(portfolio)
        // Combinar: si un valor tiene alerta de venta Y de compra, mostrar venta.
        const seen = new Set()
        const combined = []
        for (const a of [...sellAlerts, ...buyAlerts]) {
          if (!seen.has(a.security_id)) {
            combined.push(a)
            seen.add(a.security_id)
          }
        }
        setAlerts(combined)
      } catch { /* silencioso */ }
    }
    loadAlerts()
    const id = setInterval(loadAlerts, 5 * 60 * 1000)
    return () => { cancelled = true; clearInterval(id) }
  }, [user])

  return (
    <>
      {/* Cabecera superior — móvil */}
      <header className="mobile-header">
        <span className="mobile-header-brand">
          {logoUrl && <img className="mobile-header-logo" src={logoUrl} alt={appName} />}
          <span className="mobile-header-name">{appName}</span>
          <span className="mobile-header-version">v{version}</span>
        </span>
        <div style={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <AlertBell alerts={alerts} t={t} placement="down" />
          <button className="btn-ghost btn-sm" onClick={logout} style={{ fontSize: '0.8rem' }}>
            {t('nav.logout')}
          </button>
        </div>
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
              <AlertBell alerts={alerts} t={t} placement="up" />
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
