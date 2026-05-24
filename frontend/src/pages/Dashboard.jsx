import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useAppConfig } from '../context/AppContext'
import './Dashboard.css'

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

function sign(val) { return Number(val) >= 0 ? '+' : '' }
function cls(val)  { return Number(val) > 0 ? 'pos' : Number(val) < 0 ? 'neg' : 'neu' }

function SummaryCard({ label, value, clsName }) {
  return (
    <div className="card small">
      <div className={`value ${clsName ?? ''}`}>{value}</div>
      <div className="label">{label}</div>
    </div>
  )
}

function TopMoversSection({ title, market }) {
  const navigate = useNavigate()
  const { t } = useAppConfig()
  const [up, setUp]     = useState(null)
  const [down, setDown] = useState(null)

  useEffect(() => {
    Promise.all([
      api.get(`/markets/top-movers?market=${market}&n=5&direction=up`),
      api.get(`/markets/top-movers?market=${market}&n=5&direction=down`),
    ]).then(([u, d]) => { setUp(u); setDown(d) }).catch(() => {})
  }, [market])

  if (!up || !down) return null

  function MoverRow({ item }) {
    const pct = item.daily_change_pct
    return (
      <tr style={{ cursor: 'pointer' }} onClick={() => navigate(`/securities/${item.id}`)}>
        <td>
          <div className="ticker">{item.yahoo_ticker}</div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{item.name}</div>
        </td>
        <td className="num">
          {fmt(item.last_price)}
          {item.currency === 'USD' && item.last_price != null && (
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: 3 }}>$</span>
          )}
        </td>
        <td className={`num ${cls(pct)}`}>{sign(pct)}{fmt(pct)}%</td>
      </tr>
    )
  }

  function MoverTable({ items, label }) {
    if (!items.length) return null
    return (
      <div>
        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {label}
        </div>
        <table style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>{t('markets.col_name')}</th>
              <th className="num">{t('markets.col_price')}</th>
              <th className="num">{t('markets.col_change')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map(item => <MoverRow key={item.id} item={item} />)}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h2 style={{ marginBottom: 16 }}>{title}</h2>
      <div className="movers-grid">
        <div className="movers-col"><MoverTable items={up}   label={t('dashboard.up')}   /></div>
        <div className="movers-col"><MoverTable items={down} label={t('dashboard.down')} /></div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { user, logout } = useAuth()
  const { t } = useAppConfig()
  const navigate = useNavigate()
  const [positions, setPositions] = useState(null)
  const [favorites, setFavorites] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      api.get('/portfolio'),
      api.get('/favorites'),
    ])
      .then(([pos, favs]) => { setPositions(pos); setFavorites(favs) })
      .catch(err => setError(err.message))
  }, [])

  if (error) return <div className="state-error">{error}</div>
  if (positions === null) return <div className="state-loading"><div className="spinner" /></div>

  const totalValue  = positions.reduce((s, p) => s + Number(p.market_value_eur), 0)
  const totalPnL    = positions.reduce((s, p) => s + Number(p.unrealized_pnl_eur), 0)
  const totalDayEur = positions.reduce((s, p) => s + (p.daily_change_eur != null ? Number(p.daily_change_eur) : 0), 0)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h1>Hola, {user?.username?.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}</h1>
        <button className="btn-ghost btn-sm" onClick={logout}>Salir</button>
      </div>

      <div className="card-row">
        <SummaryCard label={t('portfolio.value')}     value={`${fmt(totalValue)} €`} />
        <SummaryCard label={t('portfolio.unrealized')} value={`${sign(totalPnL)}${fmt(totalPnL)} €`} clsName={cls(totalPnL)} />
        <SummaryCard label={t('portfolio.today')}     value={`${sign(totalDayEur)}${fmt(totalDayEur)} €`} clsName={cls(totalDayEur)} />
        <SummaryCard label={t('portfolio.open')}      value={positions.length} />
      </div>

      {positions.length > 0 && (
        <div className="card">
          <h2>{t('portfolio.open')}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('portfolio.col_security')}</th>
                  <th className="num">{t('portfolio.col_shares')}</th>
                  <th className="num">{t('portfolio.col_value')}</th>
                  <th className="num">{t('portfolio.col_unrealized')}</th>
                  <th className="num">{t('portfolio.col_pct')}</th>
                  <th className="num">{t('portfolio.col_daily')} %</th>
                </tr>
              </thead>
              <tbody>
                {positions.map(p => {
                  const pnl = Number(p.unrealized_pnl_eur)
                  return (
                    <tr key={p.position_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/securities/${p.security_id}`)}>
                      <td>
                        <div className="ticker">{p.yahoo_ticker}</div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{p.name}</div>
                      </td>
                      <td className="num">{fmt(p.shares, 4)}</td>
                      <td className="num">{fmt(p.market_value_eur)}</td>
                      <td className={`num ${cls(pnl)}`}>{sign(pnl)}{fmt(pnl)}</td>
                      <td className={`num ${cls(p.unrealized_pnl_pct)}`}>{sign(p.unrealized_pnl_pct)}{fmt(p.unrealized_pnl_pct)}%</td>
                      <td className={`num ${p.daily_change_pct != null ? cls(p.daily_change_pct) : 'neu'}`}>
                        {p.daily_change_pct != null ? `${sign(p.daily_change_pct)}${fmt(p.daily_change_pct)}%` : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {favorites.length > 0 && (
        <div className="card">
          <h2>{t('markets.favorites_tab')}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('markets.col_name')}</th>
                  <th className="num">{t('markets.col_price')}</th>
                  <th className="num">{t('markets.col_change')}</th>
                  <th className="num">{t('markets.col_target')}</th>
                  <th style={{ textAlign: 'center' }}>{t('markets.col_alert')}</th>
                </tr>
              </thead>
              <tbody>
                {favorites.map(f => {
                  const pct = f.daily_change_pct != null ? Number(f.daily_change_pct) : null
                  const isBuyAlert = f.target_buy_price != null
                    && f.last_price != null
                    && Number(f.last_price) <= Number(f.target_buy_price)
                  return (
                    <tr key={f.security_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/securities/${f.security_id}`)}>
                      <td>
                        <div className="ticker">{f.yahoo_ticker}</div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{f.name}</div>
                      </td>
                      <td className="num">
                        {fmt(f.last_price)}
                        {f.currency === 'USD' && f.last_price != null && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: 3 }}>$</span>
                        )}
                      </td>
                      <td className={`num ${pct == null ? 'neu' : pct > 0 ? 'pos' : pct < 0 ? 'neg' : 'neu'}`}>
                        {pct != null ? `${pct >= 0 ? '+' : ''}${fmt(pct)}%` : '—'}
                      </td>
                      <td className="num">
                        {f.target_buy_price
                          ? `${fmt(f.target_buy_price)} ${f.currency === 'USD' ? '$' : '€'}`
                          : '—'}
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        {isBuyAlert && <span className="alert-buy">¡Comprar!</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <TopMoversSection title="IBEX 35 — Movimientos del día"           market="ibex35"  />
      <TopMoversSection title="Nasdaq — Movimientos del día"            market="nasdaq"  />

      {positions.length === 0 && favorites.length === 0 && (
        <div className="state-empty" style={{ marginTop: 16 }}>
          <p>No hay datos aún.</p>
          <p style={{ marginTop: 8 }}>Añade valores en <strong>Utilidades</strong> y registra tus transacciones en <strong>Cartera</strong>.</p>
        </div>
      )}
    </div>
  )
}
