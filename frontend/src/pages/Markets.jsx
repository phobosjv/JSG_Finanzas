import { useEffect, useState } from 'react'
import { api } from '../api/client'
import SecurityTable from '../components/SecurityTable'
import SecurityCard from '../components/SecurityCard'
import { useMediaQuery } from '../hooks/useMediaQuery'

const FAV_TAB = { key: 'favoritos', label: '★ Favoritos' }

function fmtDateTime(dt) {
  if (!dt) return null
  const d = new Date(dt)
  if (isNaN(d)) return null
  return d.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
}

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

/** Sparkline SVG a partir de una lista [{date, close}] */
function Sparkline({ data, width = 140, height = 44 }) {
  if (!data || data.length < 2) return null
  const prices = data.map(d => d.close)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min || 1
  const pts = prices
    .map((p, i) => {
      const x = (i / (prices.length - 1)) * width
      const y = height - ((p - min) / range) * (height - 2) - 1
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const up = prices[prices.length - 1] >= prices[0]
  return (
    <svg width={width} height={height} style={{ display: 'block', flexShrink: 0 }}>
      <polyline
        points={pts}
        fill="none"
        stroke={up ? 'var(--green)' : 'var(--red)'}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** Cabecera con el índice del mercado */
function IndexHeader({ market }) {
  const [quote, setQuote] = useState(null)
  const [hist, setHist]   = useState([])

  useEffect(() => {
    if (market === 'favoritos') return
    setQuote(null); setHist([])
    Promise.all([
      api.get(`/markets/index-quote?market=${market}`).catch(() => null),
      api.get(`/markets/index-history?market=${market}`).catch(() => []),
    ]).then(([q, h]) => { setQuote(q); setHist(h ?? []) })
  }, [market])

  if (market === 'favoritos' || !quote) return null

  const pct = quote.daily_change_pct != null ? Number(quote.daily_change_pct) : null
  const pctCls = pct == null ? 'neu' : pct > 0 ? 'pos' : pct < 0 ? 'neg' : 'neu'

  return (
    <div className="index-header">
      <div>
        <div className="idx-name">{quote.name}</div>
        <div className="idx-ticker">{quote.ticker}</div>
      </div>
      <div className="idx-price">{fmt(quote.last_price)}</div>
      <div className={`idx-change ${pctCls}`}>
        {pct != null ? `${pct >= 0 ? '+' : ''}${fmt(pct)}%` : '—'}
      </div>
      <div className="idx-chart">
        <Sparkline data={hist} />
      </div>
    </div>
  )
}

export default function Markets() {
  const [tabs, setTabs]             = useState([])
  const [activeTab, setActiveTab]   = useState(null)
  const [securities, setSecurities] = useState([])
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const isMobile = useMediaQuery('(max-width: 767px)')

  // Load dynamic market tabs on mount
  useEffect(() => {
    api.get('/markets/list').then(mks => {
      const t = mks.map(m => ({ key: m.code, label: m.name }))
      t.push(FAV_TAB)
      setTabs(t)
      if (!activeTab) setActiveTab(t[0]?.key ?? 'favoritos')
    }).catch(() => {
      setTabs([FAV_TAB])
      if (!activeTab) setActiveTab('favoritos')
    })
  }, [])

  async function loadTab(tab) {
    setLoading(true); setError(null)
    try {
      const url = tab === 'favoritos'
        ? '/markets/overview?favorites_only=true'
        : `/markets/overview?market=${tab}`
      const data = await api.get(url)
      setSecurities(data)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  useEffect(() => {
    if (activeTab) loadTab(activeTab)
  }, [activeTab])

  function handleTabChange(tab) {
    setActiveTab(tab)
  }

  // Most recent updated_at among displayed securities
  const lastUpdated = securities.reduce((best, s) => {
    if (!s.updated_at) return best
    return !best || s.updated_at > best ? s.updated_at : best
  }, null)

  async function handleToggleFav(secId, isFav) {
    try {
      if (isFav) {
        await api.delete(`/favorites/${secId}`)
      } else {
        await api.post(`/favorites/${secId}`)
      }
      // Actualización optimista: toggle el estado en la lista local
      setSecurities(prev => {
        const updated = prev.map(s =>
          s.id === secId
            ? { ...s, is_favorite: !isFav, target_buy_price: isFav ? null : s.target_buy_price }
            : s
        )
        // En la pestaña favoritos, quitar el elemento si se desmarca
        if (activeTab === 'favoritos' && isFav) {
          return updated.filter(s => s.id !== secId)
        }
        return updated
      })
    } catch { /* ignorar: el estado no cambia */ }
  }

  function handleTargetUpdate(secId, newPrice) {
    setSecurities(prev =>
      prev.map(s => s.id === secId ? { ...s, target_buy_price: newPrice } : s)
    )
  }

  return (
    <div>
      <h1>Mercados</h1>

      {/* Pestañas dinámicas */}
      <div className="tabs">
        {tabs.map(t => (
          <button
            key={t.key}
            className={`tab-btn ${activeTab === t.key ? 'active' : ''}`}
            onClick={() => handleTabChange(t.key)}
          >
            {t.label}
            {t.key === 'favoritos' && securities.length > 0 && activeTab === 'favoritos'
              ? ` (${securities.length})` : ''}
          </button>
        ))}
      </div>

      {/* Cabecera del índice */}
      {activeTab && <IndexHeader market={activeTab} />}

      {/* Última actualización */}
      {lastUpdated && (
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 8, textAlign: 'right' }}>
          Precios actualizados: {fmtDateTime(lastUpdated)}
        </div>
      )}

      {/* Contenido */}
      {error ? (
        <div className="state-error">{error}</div>
      ) : loading ? (
        <div className="state-loading"><div className="spinner" /></div>
      ) : securities.length === 0 ? (
        <div className="state-empty">
          {activeTab === 'favoritos'
            ? 'Aún no has marcado ningún valor como favorito. Pulsa ☆ en cualquier mercado.'
            : 'No hay valores en este mercado. El administrador puede añadirlos en el panel de administración.'}
        </div>
      ) : isMobile ? (
        securities.map(s => (
          <SecurityCard
            key={s.id}
            sec={s}
            favoritesTab={activeTab === 'favoritos'}
            onToggleFav={handleToggleFav}
            onTargetUpdate={handleTargetUpdate}
          />
        ))
      ) : (
        <div className="card">
          <SecurityTable
            securities={securities}
            favoritesTab={activeTab === 'favoritos'}
            onToggleFav={handleToggleFav}
            onTargetUpdate={handleTargetUpdate}
          />
        </div>
      )}
    </div>
  )
}
