import { useState, useEffect, useRef } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
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

// Mini-modal inline para notificaciones de solicitud (aprobada/rechazada/pendiente).
// Se muestra dentro del popup de la campana.
function NotificationDetail({ notif, t, onDismiss, onReply }) {
  const [showReply, setShowReply] = useState(false)
  const [replyText, setReplyText] = useState('')
  const [sending, setSending]     = useState(false)

  async function handleSendReply() {
    if (!replyText.trim()) return
    setSending(true)
    try {
      await api.post(`/notifications/${notif.id}/reply`, { message: replyText.trim() })
      onReply()
    } catch { /* ignorar */ } finally { setSending(false) }
  }

  return (
    <div style={{
      padding: '10px 14px',
      borderBottom: '1px solid var(--border)',
      fontSize: '0.82rem',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{notif.title}</div>
      <div style={{ color: 'var(--text-muted)', marginBottom: 8 }}>{notif.body}</div>

      {showReply ? (
        <div>
          <textarea
            rows={3}
            value={replyText}
            onChange={e => setReplyText(e.target.value)}
            placeholder={t('nav.notif_reply_placeholder')}
            style={{
              width: '100%', boxSizing: 'border-box', resize: 'vertical',
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 4, padding: '6px 8px', color: 'var(--text)', fontSize: '0.8rem',
              marginBottom: 6,
            }}
          />
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn-ghost btn-sm" onClick={() => setShowReply(false)} disabled={sending}>
              {t('requests.cancel')}
            </button>
            <button
              className="btn-primary btn-sm"
              onClick={handleSendReply}
              disabled={sending || !replyText.trim()}
            >
              {t('nav.notif_send_reply')}
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button className="btn-ghost btn-sm" onClick={onDismiss} style={{ fontSize: '0.75rem' }}>
            {t('nav.notif_dismiss')}
          </button>
          {!['request_pending', 'user_expired', 'renewal_request'].includes(notif.type) && (
            <button
              className="btn-secondary btn-sm"
              onClick={() => setShowReply(true)}
              style={{ fontSize: '0.75rem' }}
            >
              {t('nav.notif_reply')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// Componente campana con popup de alertas y notificaciones de servidor.
// placement='up': el popup abre hacia arriba (sidebar-footer).
// placement='down': el popup abre hacia abajo (mobile-header).
function AlertBell({ alerts, serverNotifs, t, placement, onNotifsChanged }) {
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

  const totalCount = alerts.length + serverNotifs.length
  const hasAlerts  = totalCount > 0

  async function handleDismiss(notifId) {
    try {
      await api.delete(`/notifications/${notifId}`)
      onNotifsChanged()
    } catch { /* ignorar */ }
  }

  function handleReply() {
    onNotifsChanged()
  }

  // Icono de badge según tipo de notificación de solicitud
  function notifBadge(type) {
    if (type === 'request_pending')  return { label: t('nav.notif_request_pending'),  color: '#d97706' }
    if (type === 'request_approved') return { label: t('nav.notif_request_approved'), color: 'var(--green)' }
    if (type === 'request_rejected') return { label: t('nav.notif_request_rejected'), color: 'var(--red)' }
    if (type === 'user_expired')     return { label: t('nav.notif_user_expired'),      color: '#9333ea' }
    if (type === 'renewal_request')  return { label: t('nav.notif_renewal_request'),   color: '#0ea5e9' }
    return { label: type, color: 'var(--text-muted)' }
  }

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
            {totalCount > 9 ? '9+' : totalCount}
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

          {totalCount === 0 ? (
            <div style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              {t('nav.alerts_empty')}
            </div>
          ) : (
            <>
              {/* Notificaciones de servidor (solicitudes) */}
              {serverNotifs.map(n => (
                <NotificationDetail
                  key={`notif-${n.id}`}
                  notif={n}
                  t={t}
                  onDismiss={() => { handleDismiss(n.id); setOpen(false) }}
                  onReply={() => { handleReply(); setOpen(false) }}
                />
              ))}

              {/* Alertas de precio (existentes) */}
              {alerts.map(a => (
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
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default function Navigation() {
  const { user, logout } = useAuth()
  const { appName, logoUrl, theme, toggleTheme, t } = useAppConfig()
  const [alerts, setAlerts]           = useState([])
  const [serverNotifs, setServerNotifs] = useState([])
  const location = useLocation()

  async function loadAlerts() {
    try {
      const [portfolio, favorites, notifs] = await Promise.all([
        api.get('/portfolio'),
        api.get('/favorites'),
        api.get('/notifications'),
      ])
      const buyAlerts  = computeBuyAlerts(favorites)
      const sellAlerts = computeSellAlerts(portfolio)
      // Combinar alertas de precio: venta tiene prioridad sobre compra para el mismo valor
      const seen = new Set()
      const combined = []
      for (const a of [...sellAlerts, ...buyAlerts]) {
        if (!seen.has(a.security_id)) {
          combined.push(a)
          seen.add(a.security_id)
        }
      }
      setAlerts(combined)
      setServerNotifs(Array.isArray(notifs) ? notifs : [])
    } catch { /* silencioso */ }
  }

  useEffect(() => {
    if (!user) return
    let cancelled = false
    async function load() {
      if (cancelled) return
      await loadAlerts()
    }
    load()
    const id = setInterval(load, 5 * 60 * 1000)
    return () => { cancelled = true; clearInterval(id) }
  }, [user, location.pathname])

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
          <AlertBell
            alerts={alerts}
            serverNotifs={serverNotifs}
            t={t}
            placement="down"
            onNotifsChanged={loadAlerts}
          />
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
              <AlertBell
                alerts={alerts}
                serverNotifs={serverNotifs}
                t={t}
                placement="up"
                onNotifsChanged={loadAlerts}
              />
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
