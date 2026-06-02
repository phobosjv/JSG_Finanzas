import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useAppConfig } from '../context/AppContext'
import PortfolioChartsPanel from '../components/PortfolioChartsPanel'
import AssetTypeFilter, { matchesTypes, presentTypes } from '../components/AssetTypeFilter'
import './Dashboard.css'

// ─── Utilidades ──────────────────────────────────────────────────────────────

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

function sign(val) { return Number(val) >= 0 ? '+' : '' }
function cls(val)  { return Number(val) > 0 ? 'pos' : Number(val) < 0 ? 'neg' : 'neu' }

// ─── Configuración del dashboard ─────────────────────────────────────────────

const DEFAULT_SECTIONS = [
  { id: 'kpis',      enabled: true,  order: 0 },
  { id: 'positions', enabled: true,  order: 1 },
  { id: 'favorites', enabled: true,  order: 2 },
  { id: 'movers',    enabled: true,  order: 3 },
  { id: 'charts',    enabled: false, order: 4 },
]

const DEFAULT_CONFIG = {
  sections:       DEFAULT_SECTIONS,
  moversMarkets:  null,          // null = todos los mercados disponibles
  chartsVisible:  ['distribution', 'pnl_pct', 'history'],
}

function loadConfig() {
  try {
    const raw = localStorage.getItem('dashboardConfig')
    if (!raw) return DEFAULT_CONFIG
    const parsed = JSON.parse(raw)
    // Fusionar con default por si alguna sección nueva aún no existe en el config guardado
    const storedIds = parsed.sections.map(s => s.id)
    const missing = DEFAULT_SECTIONS.filter(s => !storedIds.includes(s.id))
    const merged = [...parsed.sections, ...missing.map((s, i) => ({
      ...s, order: parsed.sections.length + i,
    }))]
    return { ...DEFAULT_CONFIG, ...parsed, sections: merged }
  } catch {
    return DEFAULT_CONFIG
  }
}

function saveConfig(cfg) {
  localStorage.setItem('dashboardConfig', JSON.stringify(cfg))
}

// ─── Componente KPIs ─────────────────────────────────────────────────────────

function SummaryCard({ label, value, clsName }) {
  return (
    <div className="card small">
      <div className={`value ${clsName ?? ''}`}>{value}</div>
      <div className="label">{label}</div>
    </div>
  )
}

function KpisSection({ positions, t }) {
  const totalValue  = positions.reduce((s, p) => s + Number(p.market_value_eur), 0)
  const totalPnL    = positions.reduce((s, p) => s + Number(p.unrealized_pnl_eur), 0)
  const totalDayEur = positions.reduce((s, p) => s + (p.daily_change_eur != null ? Number(p.daily_change_eur) : 0), 0)
  return (
    <div className="card-row">
      <SummaryCard label={t('portfolio.value')}      value={`${fmt(totalValue)} €`} />
      <SummaryCard label={t('portfolio.unrealized')} value={`${sign(totalPnL)}${fmt(totalPnL)} €`} clsName={cls(totalPnL)} />
      <SummaryCard label={t('portfolio.today')}      value={`${sign(totalDayEur)}${fmt(totalDayEur)} €`} clsName={cls(totalDayEur)} />
      <SummaryCard label={t('portfolio.open')}       value={positions.length} />
    </div>
  )
}

// ─── Componente posiciones abiertas ──────────────────────────────────────────

function PositionsSection({ positions, navigate, t }) {
  if (positions.length === 0) return null
  return (
    <div className="card" style={{ marginTop: 16 }}>
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
  )
}

// ─── Componente favoritos (scrollable) ───────────────────────────────────────

function FavoritesSection({ favorites, navigate, t }) {
  if (favorites.length === 0) return null
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h2>{t('markets.favorites_tab')}</h2>
      <div className="table-wrap favorites-scroll">
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
  )
}

// ─── Componente top movers ────────────────────────────────────────────────────

function MoverCard({ market, t, navigate }) {
  const [up, setUp]     = useState(null)
  const [down, setDown] = useState(null)

  useEffect(() => {
    let cancelled = false
    function load() {
      Promise.all([
        api.get(`/markets/top-movers?market=${market.code}&n=5&direction=up`),
        api.get(`/markets/top-movers?market=${market.code}&n=5&direction=down`),
      ]).then(([u, d]) => { if (!cancelled) { setUp(u); setDown(d) } })
        .catch(() => { if (!cancelled) { setUp([]); setDown([]) } })
    }
    // Refresco bajo demanda de los snapshots del mercado (background en el
    // servidor, throttled 15 min y con tope de tamaño). Muestra ya lo que hay
    // en BD y refresca una vez tras un pequeño retardo por si terminó (mercados
    // pequeños como IBEX). Los grandes quedarán frescos en la siguiente visita.
    api.post(`/markets/${market.code}/refresh-movers`).catch(() => {})
    load()
    const tmr = setTimeout(load, 7000)
    return () => { cancelled = true; clearTimeout(tmr) }
  }, [market.code])

  if (up === null || down === null) return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="state-loading" style={{ height: 80 }}><div className="spinner" /></div>
    </div>
  )

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
    if (!items || items.length === 0) return (
      <div>
        <div className="movers-label">{label}</div>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem', padding: '8px 0' }}>
          {t('dashboard.movers_none')}
        </div>
      </div>
    )
    return (
      <div>
        <div className="movers-label">{label}</div>
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
      <h2 style={{ marginBottom: 16 }}>{market.name} — {t('dashboard.movers_title')}</h2>
      <div className="movers-grid">
        <div className="movers-col"><MoverTable items={up}   label={t('dashboard.up')}   /></div>
        <div className="movers-col"><MoverTable items={down} label={t('dashboard.down')} /></div>
      </div>
    </div>
  )
}

function MoversSection({ allMarkets, moversMarkets, t, navigate }) {
  const markets = Array.isArray(allMarkets) ? allMarkets : []
  // null = todos; array = solo los seleccionados
  const visible = moversMarkets === null
    ? markets
    : markets.filter(m => moversMarkets.includes(m.code))

  if (visible.length === 0) return null

  return (
    <>
      {visible.map(m => (
        <MoverCard key={m.code} market={m} t={t} navigate={navigate} />
      ))}
    </>
  )
}

// ─── Sección gráficos ─────────────────────────────────────────────────────────

function ChartsSection({ positions, history, chartsVisible, t, navigate }) {
  if (!positions || positions.length === 0) return null
  return (
    <div style={{ marginTop: 16 }}>
      <PortfolioChartsPanel
        positions={positions}
        history={history}
        chartsVisible={chartsVisible}
        t={t}
        navigate={navigate}
      />
    </div>
  )
}

// ─── Modal de configuración ───────────────────────────────────────────────────

const SECTION_LABEL_KEYS = {
  kpis:      'dashboard.section_kpis',
  positions: 'dashboard.section_positions',
  favorites: 'dashboard.section_favorites',
  movers:    'dashboard.section_movers',
  charts:    'dashboard.section_charts',
}

const CHART_OPTIONS = [
  { id: 'distribution', labelKey: 'portfolio.chart_distribution' },
  { id: 'pnl_pct',      labelKey: 'portfolio.chart_pnl_pct' },
  { id: 'history',      labelKey: 'portfolio.chart_history' },
]

function DashboardConfigModal({ config, onSave, onClose, allMarkets, t }) {
  // Copia local mutable del config
  const [sections, setSections]             = useState(() => [...config.sections].sort((a, b) => a.order - b.order))
  const [moversMarkets, setMoversMarkets]   = useState(config.moversMarkets)
  const [chartsVisible, setChartsVisible]   = useState(config.chartsVisible)

  const safeMarkets = Array.isArray(allMarkets) ? allMarkets : []

  // Cuando allMarkets carga, inicializar moversMarkets si es null (mostrar todos)
  const effectiveMoverMarkets = moversMarkets === null
    ? safeMarkets.map(m => m.code)
    : moversMarkets

  function toggleSection(id) {
    setSections(prev => prev.map(s => s.id === id ? { ...s, enabled: !s.enabled } : s))
  }

  function moveSection(id, dir) {
    setSections(prev => {
      const arr  = [...prev]
      const idx  = arr.findIndex(s => s.id === id)
      const swap = idx + dir
      if (swap < 0 || swap >= arr.length) return arr
      ;[arr[idx], arr[swap]] = [arr[swap], arr[idx]]
      return arr.map((s, i) => ({ ...s, order: i }))
    })
  }

  function toggleMoverMarket(code) {
    const current = effectiveMoverMarkets
    const next = current.includes(code)
      ? current.filter(c => c !== code)
      : [...current, code]
    // si todos seleccionados → volver a null (todos por defecto)
    setMoversMarkets(next.length === safeMarkets.length ? null : next)
  }

  function toggleChart(id) {
    setChartsVisible(prev =>
      prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]
    )
  }

  function handleSave() {
    onSave({
      sections: sections.map((s, i) => ({ ...s, order: i })),
      moversMarkets,
      chartsVisible,
    })
    onClose()
  }

  return (
    <div className="db-modal-overlay" onClick={onClose}>
      <div className="db-modal" onClick={e => e.stopPropagation()}>
        <div className="db-modal-header">
          <h2>{t('dashboard.configure')}</h2>
          <button className="db-modal-close" onClick={onClose}>✕</button>
        </div>

        {/* Secciones */}
        <div className="db-modal-section">
          <div className="db-modal-label">{t('dashboard.config_sections')}</div>
          {sections.map((s, idx) => (
            <div key={s.id} className="db-config-row">
              <label className="db-config-check">
                <input
                  type="checkbox"
                  checked={s.enabled}
                  onChange={() => toggleSection(s.id)}
                />
                <span>{t(SECTION_LABEL_KEYS[s.id])}</span>
              </label>
              <div className="db-reorder-btns">
                <button disabled={idx === 0} onClick={() => moveSection(s.id, -1)}>▲</button>
                <button disabled={idx === sections.length - 1} onClick={() => moveSection(s.id, 1)}>▼</button>
              </div>
            </div>
          ))}
        </div>

        {/* Mercados para movers */}
        {safeMarkets.length > 0 && (
          <div className="db-modal-section">
            <div className="db-modal-label">{t('dashboard.config_movers_markets')}</div>
            {safeMarkets.map(m => (
              <label key={m.code} className="db-config-check" style={{ marginBottom: 6, display: 'flex', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={effectiveMoverMarkets.includes(m.code)}
                  onChange={() => toggleMoverMarket(m.code)}
                />
                <span>{m.name}</span>
              </label>
            ))}
          </div>
        )}

        {/* Gráficos a mostrar */}
        <div className="db-modal-section">
          <div className="db-modal-label">{t('dashboard.config_charts')}</div>
          {CHART_OPTIONS.map(opt => (
            <label key={opt.id} className="db-config-check" style={{ marginBottom: 6, display: 'flex', gap: 8 }}>
              <input
                type="checkbox"
                checked={chartsVisible.includes(opt.id)}
                onChange={() => toggleChart(opt.id)}
              />
              <span>{t(opt.labelKey)}</span>
            </label>
          ))}
        </div>

        <div className="db-modal-footer">
          <button className="btn-primary" onClick={handleSave}>{t('dashboard.config_save')}</button>
        </div>
      </div>
    </div>
  )
}

// ─── Dashboard principal ──────────────────────────────────────────────────────

export default function Dashboard() {
  const { user, logout } = useAuth()
  const { t }            = useAppConfig()
  const navigate         = useNavigate()

  const [positions,  setPositions]  = useState(null)
  const [favorites,  setFavorites]  = useState([])
  const [history,    setHistory]    = useState([])
  const [allMarkets, setAllMarkets] = useState([])
  const [error,      setError]      = useState(null)
  const [configOpen, setConfigOpen] = useState(false)
  const [config,     setConfig]     = useState(loadConfig)
  const [segTypes,   setSegTypes]   = useState(() => {
    try { return JSON.parse(localStorage.getItem('dashboardSegTypes')) || [] } catch { return [] }
  })

  // Carga inicial: portfolio, favoritos y mercados
  useEffect(() => {
    Promise.all([
      api.get('/portfolio'),
      api.get('/favorites'),
      api.get('/markets/list'),
    ])
      .then(([pos, favs, mkts]) => {
        setPositions(pos)
        setFavorites(favs)
        setAllMarkets(mkts)
        // Sanear selección persistida contra los tipos realmente presentes.
        const avail = presentTypes(pos || [])
        const clean = segTypes.filter(tp => avail.includes(tp))
        if (clean.length !== segTypes.length) changeSeg(clean)
      })
      .catch(err => setError(err.message))
  }, [])

  // El histórico se agrega en el backend; se re-pide al cambiar la segmentación.
  useEffect(() => {
    const qs = segTypes.length ? `?types=${segTypes.join(',')}` : ''
    api.get(`/portfolio/history${qs}`).then(setHistory).catch(() => setHistory([]))
  }, [segTypes])

  function changeSeg(next) {
    setSegTypes(next)
    localStorage.setItem('dashboardSegTypes', JSON.stringify(next))
  }

  function handleSaveConfig(newConfig) {
    setConfig(newConfig)
    saveConfig(newConfig)
  }

  if (error)            return <div className="state-error">{error}</div>
  if (positions === null) return <div className="state-loading"><div className="spinner" /></div>

  // Secciones ordenadas y activas
  const orderedSections = [...config.sections].sort((a, b) => a.order - b.order)

  const showEmpty = positions.length === 0 && favorites.length === 0

  // Posiciones filtradas por la segmentación (afecta a KPIs, posiciones y gráficos).
  const available  = presentTypes(positions)
  const fPositions = positions.filter(p => matchesTypes(p, segTypes))

  function renderSection(s) {
    if (!s.enabled) return null
    switch (s.id) {
      case 'kpis':
        return <KpisSection key="kpis" positions={fPositions} t={t} />
      case 'positions':
        return <PositionsSection key="positions" positions={fPositions} navigate={navigate} t={t} />
      case 'favorites':
        return <FavoritesSection key="favorites" favorites={favorites} navigate={navigate} t={t} />
      case 'movers':
        return (
          <MoversSection
            key="movers"
            allMarkets={allMarkets}
            moversMarkets={config.moversMarkets}
            t={t}
            navigate={navigate}
          />
        )
      case 'charts':
        return (
          <ChartsSection
            key="charts"
            positions={fPositions}
            history={history}
            chartsVisible={config.chartsVisible}
            t={t}
            navigate={navigate}
          />
        )
      default:
        return null
    }
  }

  return (
    <div>
      {/* Cabecera */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h1>{t('dashboard.hello').replace('{name}',
          user?.username?.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') ?? ''
        )}</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-ghost btn-sm" onClick={() => setConfigOpen(true)} title={t('dashboard.configure')}>⚙</button>
          <button className="btn-ghost btn-sm" onClick={logout}>{t('dashboard.logout')}</button>
        </div>
      </div>

      {/* Segmentador por tipo de producto (afecta a resumen, posiciones y gráficos) */}
      {positions.length > 0 && (
        <AssetTypeFilter value={segTypes} available={available} onChange={changeSeg} />
      )}

      {/* Secciones configurables */}
      {orderedSections.map(s => renderSection(s))}

      {/* Estado vacío */}
      {showEmpty && (
        <div className="state-empty" style={{ marginTop: 16 }}>
          <p>{t('dashboard.empty_msg')}</p>
          <p style={{ marginTop: 8 }}>
            {t('dashboard.empty_hint')}
          </p>
        </div>
      )}

      {/* Modal de configuración */}
      {configOpen && (
        <DashboardConfigModal
          config={config}
          onSave={handleSaveConfig}
          onClose={() => setConfigOpen(false)}
          allMarkets={allMarkets}
          t={t}
        />
      )}
    </div>
  )
}
