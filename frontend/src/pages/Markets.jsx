import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'
import SecurityTable from '../components/SecurityTable'
import SecurityCard from '../components/SecurityCard'
import { useMediaQuery } from '../hooks/useMediaQuery'

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
  const { t } = useAppConfig()
  const [tabs, setTabs]             = useState([])
  const [activeTab, setActiveTab]   = useState(null)
  const [securities, setSecurities] = useState([])
  const [search, setSearch]         = useState('')
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const isMobile = useMediaQuery('(max-width: 767px)')

  // Construir la pestaña Favoritos con la etiqueta traducida
  const FAV_TAB = { key: 'favoritos', label: t('markets.favorites_tab') }

  // Load dynamic market tabs on mount
  useEffect(() => {
    api.get('/markets/list').then(mks => {
      const tabs = mks.map(m => ({ key: m.code, label: m.name }))
      tabs.push(FAV_TAB)
      setTabs(tabs)
      if (!activeTab) setActiveTab(tabs[0]?.key ?? 'favoritos')
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
    setSearch('')           // limpiar buscador al cambiar de pestaña
  }

  // Filtro local: ticker o nombre, case-insensitive
  const q = search.trim().toLowerCase()
  const filtered = q
    ? securities.filter(s =>
        s.yahoo_ticker.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q)
      )
    : securities

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
      setSecurities(prev => {
        const updated = prev.map(s =>
          s.id === secId
            ? { ...s, is_favorite: !isFav, target_buy_price: isFav ? null : s.target_buy_price }
            : s
        )
        if (activeTab === 'favoritos' && isFav) {
          return updated.filter(s => s.id !== secId)
        }
        return updated
      })
    } catch { /* ignorar */ }
  }

  function handleTargetUpdate(secId, newPrice) {
    setSecurities(prev =>
      prev.map(s => s.id === secId ? { ...s, target_buy_price: newPrice } : s)
    )
  }

  return (
    <div>
      <h1>{t('markets.title')}</h1>

      {/* Pestañas dinámicas con scroll horizontal */}
      <div className="tabs">
        {tabs.map(tab => (
          <button
            key={tab.key}
            className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.key)}
          >
            {tab.label}
            {tab.key === 'favoritos' && securities.length > 0 && activeTab === 'favoritos'
              ? ` (${securities.length})` : ''}
          </button>
        ))}
      </div>

      {/* Cabecera del índice */}
      {activeTab && <IndexHeader market={activeTab} />}

      {/* Fila: última actualización + buscador */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
        {lastUpdated && (
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', flex: '0 0 auto' }}>
            {t('markets.updated')} {fmtDateTime(lastUpdated)}
          </div>
        )}
        <div style={{ flex: 1, minWidth: 180, position: 'relative' }}>
          <span style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-muted)', fontSize: '0.85rem', pointerEvents: 'none',
          }}>🔍</span>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t('markets.search_placeholder')}
            style={{
              width: '100%',
              padding: '6px 32px 6px 30px',
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              color: 'var(--text)',
              fontSize: '0.88rem',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              style={{
                position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                background: 'none', border: 'none', color: 'var(--text-muted)',
                cursor: 'pointer', fontSize: '0.9rem', padding: '0 2px', lineHeight: 1,
              }}
              title={t('markets.search_clear')}
            >✕</button>
          )}
        </div>
        {q && (
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', flex: '0 0 auto' }}>
            {t('markets.search_results')
              .replace('{n}', filtered.length)
              .replace('{total}', securities.length)}
          </div>
        )}
      </div>

      {/* Contenido */}
      {error ? (
        <div className="state-error">{error}</div>
      ) : loading ? (
        <div className="state-loading"><div className="spinner" /></div>
      ) : securities.length === 0 ? (
        <div className="state-empty">
          {activeTab === 'favoritos'
            ? t('markets.no_favorites')
            : t('markets.no_securities')}
        </div>
      ) : filtered.length === 0 ? (
        <div className="state-empty">{t('markets.search_no_results')}</div>
      ) : isMobile ? (
        filtered.map(s => (
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
            securities={filtered}
            favoritesTab={activeTab === 'favoritos'}
            onToggleFav={handleToggleFav}
            onTargetUpdate={handleTargetUpdate}
          />
        </div>
      )}
    </div>
  )
}
