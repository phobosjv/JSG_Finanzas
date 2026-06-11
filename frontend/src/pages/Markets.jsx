import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'
import { useAuth } from '../context/AuthContext'
import SecurityTable from '../components/SecurityTable'
import SecurityCard from '../components/SecurityCard'
import { ASSET_TYPE_ORDER } from '../components/AssetTypeFilter'
import { useMediaQuery } from '../hooks/useMediaQuery'
import AddProductModal from '../components/AddProductModal'
import CatalogMessageModal from '../components/CatalogMessageModal'
import './Dashboard.css'

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

// ─── Config de mercados visibles ──────────────────────────────────────────────

function loadMarketsConfig() {
  try {
    const raw = localStorage.getItem('marketsConfig')
    if (!raw) return { hiddenMarkets: [] }
    const parsed = JSON.parse(raw)
    return { hiddenMarkets: Array.isArray(parsed.hiddenMarkets) ? parsed.hiddenMarkets : [] }
  } catch {
    return { hiddenMarkets: [] }
  }
}

function saveMarketsConfig(cfg) {
  localStorage.setItem('marketsConfig', JSON.stringify(cfg))
}

// ─── Modal de configuración de mercados ───────────────────────────────────────

function MarketsConfigModal({ allMarkets, hiddenMarkets, onSave, onClose, t }) {
  const [hidden, setHidden] = useState(hiddenMarkets)

  const typeOf = m => m.market_type || 'stock'
  const typesPresent = ASSET_TYPE_ORDER.filter(tp => allMarkets.some(m => typeOf(m) === tp))

  function toggleMarket(code) {
    setHidden(prev =>
      prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]
    )
  }

  function handleSave() {
    onSave(hidden)
    onClose()
  }

  return (
    <div className="db-modal-overlay" onClick={onClose}>
      <div className="db-modal" onClick={e => e.stopPropagation()}>
        <div className="db-modal-header">
          <h2>{t('markets.configure')}</h2>
          <button className="db-modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="db-modal-section">
          <div className="db-modal-label">{t('markets.config_visible_markets')}</div>
          {typesPresent.map(tp => {
            const mksOfType = allMarkets.filter(m => typeOf(m) === tp)
            return (
              <div key={tp} style={{ marginBottom: 12 }}>
                {typesPresent.length > 1 && (
                  <div style={{
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    color: 'var(--text-muted)',
                    marginBottom: 6,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                  }}>
                    {t(`seg.${tp}`)}
                  </div>
                )}
                {mksOfType.map(m => (
                  <label key={m.code} className="db-config-check" style={{ marginBottom: 6, display: 'flex', gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={!hidden.includes(m.code)}
                      onChange={() => toggleMarket(m.code)}
                    />
                    <span>{m.name}</span>
                  </label>
                ))}
              </div>
            )
          })}
        </div>

        <div className="db-modal-footer">
          <button className="btn-primary" onClick={handleSave}>{t('dashboard.config_save')}</button>
        </div>
      </div>
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

export default function Markets() {
  const { t } = useAppConfig()
  const { user } = useAuth()
  const [marketsList, setMarketsList] = useState([])
  const [activeType, setActiveType]     = useState(null)  // tipo de producto | 'favoritos'
  const [activeMarket, setActiveMarket] = useState(null)  // código de mercado (null en favoritos)
  const [securities, setSecurities] = useState([])
  const [search, setSearch]         = useState('')
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const [showAddModal, setShowAddModal]         = useState(false)
  const [showMessageModal, setShowMessageModal] = useState(false)
  const [configOpen, setConfigOpen] = useState(false)
  const [hiddenMarkets, setHiddenMarkets] = useState(() => loadMarketsConfig().hiddenMarkets)
  const isMobile = useMediaQuery('(max-width: 767px)')

  const typeOf = m => m.market_type || 'stock'

  // Mercados visibles según la configuración del usuario
  const visibleMarketsList = marketsList.filter(m => !hiddenMarkets.includes(m.code))

  // Cargar mercados al montar y elegir el primer tipo/mercado disponible
  useEffect(() => {
    const initHidden = loadMarketsConfig().hiddenMarkets
    api.get('/markets/list').then(mks => {
      setMarketsList(mks)
      const visible = mks.filter(m => !initHidden.includes(m.code))
      const present = ASSET_TYPE_ORDER.filter(tp => visible.some(m => typeOf(m) === tp))
      if (present.length) {
        setActiveType(present[0])
        setActiveMarket(visible.find(m => typeOf(m) === present[0])?.code ?? null)
      } else {
        setActiveType('favoritos')
      }
    }).catch(() => setActiveType('favoritos'))
  }, [])

  // (Re)cargar valores al cambiar de tipo/mercado
  useEffect(() => {
    if (!activeType) return
    const url = activeType === 'favoritos'
      ? '/markets/overview?favorites_only=true'
      : (activeMarket ? `/markets/overview?market=${activeMarket}` : null)
    if (!url) { setSecurities([]); setLoading(false); return }
    setLoading(true); setError(null)
    api.get(url)
      .then(setSecurities)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [activeType, activeMarket])

  // Tipos presentes (primer nivel) y mercados del tipo activo (segundo nivel)
  const typesPresent = ASSET_TYPE_ORDER.filter(tp => visibleMarketsList.some(m => typeOf(m) === tp))
  const marketsOfType = activeType && activeType !== 'favoritos'
    ? visibleMarketsList.filter(m => typeOf(m) === activeType)
    : []

  function handleTypeChange(type) {
    setActiveType(type)
    setSearch('')
    if (type !== 'favoritos') {
      setActiveMarket(visibleMarketsList.find(m => typeOf(m) === type)?.code ?? null)
    }
  }

  function handleMarketChange(code) {
    setActiveMarket(code)
    setSearch('')
  }

  function handleConfigSave(newHidden) {
    saveMarketsConfig({ hiddenMarkets: newHidden })
    setHiddenMarkets(newHidden)

    // Auto-fix la selección activa si el mercado/tipo activo queda oculto
    const visible = marketsList.filter(m => !newHidden.includes(m.code))
    if (activeType && activeType !== 'favoritos') {
      const typeVisible = visible.filter(m => typeOf(m) === activeType)
      if (typeVisible.length === 0) {
        // El tipo activo ya no tiene mercados visibles → saltar al primer tipo visible
        const firstType = ASSET_TYPE_ORDER.find(tp => visible.some(m => typeOf(m) === tp))
        if (firstType) {
          setActiveType(firstType)
          setActiveMarket(visible.find(m => typeOf(m) === firstType)?.code ?? null)
        } else {
          setActiveType('favoritos')
          setActiveMarket(null)
        }
      } else if (activeMarket && newHidden.includes(activeMarket)) {
        // El mercado activo queda oculto → primer visible del mismo tipo
        setActiveMarket(typeVisible[0].code)
      }
    }
  }

  // Filtro local: ticker o nombre, case-insensitive
  const q = search.trim().toLowerCase()
  const filtered = q
    ? securities.filter(s =>
        s.yahoo_ticker.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q) ||
        (s.isin || '').toLowerCase().includes(q)
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
        if (activeType === 'favoritos' && isFav) {
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
      {/* Cabecera con título y botón de configuración */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <h1 style={{ margin: 0 }}>{t('markets.title')}</h1>
        {marketsList.length > 0 && (
          <button
            className="btn-ghost btn-sm"
            onClick={() => setConfigOpen(true)}
            title={t('markets.configure')}
          >
            ⚙
          </button>
        )}
      </div>

      {/* Primer nivel: tipo de producto + Favoritos */}
      <div className="tabs">
        {typesPresent.map(tp => (
          <button
            key={tp}
            className={`tab-btn ${activeType === tp ? 'active' : ''}`}
            onClick={() => handleTypeChange(tp)}
          >
            {t(`seg.${tp}`)}
          </button>
        ))}
        <button
          className={`tab-btn ${activeType === 'favoritos' ? 'active' : ''}`}
          onClick={() => handleTypeChange('favoritos')}
        >
          ★ {t('markets.favorites_tab')}
          {securities.length > 0 && activeType === 'favoritos' ? ` (${securities.length})` : ''}
        </button>
      </div>

      {/* Segundo nivel: mercados del tipo activo (solo si hay más de uno) */}
      {marketsOfType.length > 1 && (
        <div className="tabs tabs-sub">
          {marketsOfType.map(m => (
            <button
              key={m.code}
              className={`tab-btn ${activeMarket === m.code ? 'active' : ''}`}
              onClick={() => handleMarketChange(m.code)}
            >
              {m.name}
            </button>
          ))}
        </div>
      )}

      {/* Cabecera del índice (solo en mercados reales) */}
      {activeType !== 'favoritos' && activeMarket && <IndexHeader market={activeMarket} />}

      {/* Hint de navegación */}
      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 6 }}>
        {t('markets.nav_hint')}
      </div>

      {/* Fila: última actualización + buscador */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
        {lastUpdated && (
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', flex: '0 0 auto' }}>
            <div>{t('markets.updated')} {fmtDateTime(lastUpdated)}</div>
            <div style={{ fontSize: '0.72rem', opacity: 0.7 }}>{t('markets.updated_note')}</div>
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
          {activeType === 'favoritos'
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
            favoritesTab={activeType === 'favoritos'}
            onToggleFav={handleToggleFav}
            onTargetUpdate={handleTargetUpdate}
          />
        ))
      ) : (
        <div className="card">
          <SecurityTable
            securities={filtered}
            favoritesTab={activeType === 'favoritos'}
            onToggleFav={handleToggleFav}
            onTargetUpdate={handleTargetUpdate}
          />
        </div>
      )}

      {/* Hint para agregar producto — solo usuarios no-admin */}
      {user && !user.is_admin && (
        <div style={{
          marginTop: 16,
          padding: '10px 14px',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          fontSize: '0.82rem',
          color: 'var(--text-muted)',
        }}>
          {t('markets.not_found_hint')}{' '}
          <button
            className="btn-link"
            style={{ fontSize: '0.82rem', textDecoration: 'underline', cursor: 'pointer', background: 'none', border: 'none', color: 'var(--accent)', padding: 0 }}
            onClick={() => setShowAddModal(true)}
          >
            {t('markets.not_found_add')}
          </button>
          {', '}
          {t('markets.not_found_or')}{' '}
          <button
            className="btn-link"
            style={{ fontSize: '0.82rem', textDecoration: 'underline', cursor: 'pointer', background: 'none', border: 'none', color: 'var(--accent)', padding: 0 }}
            onClick={() => setShowMessageModal(true)}
          >
            {t('markets.not_found_contact')}
          </button>.
        </div>
      )}

      {showAddModal && (
        <AddProductModal
          defaultMarket={activeMarket}
          onClose={() => setShowAddModal(false)}
        />
      )}
      {showMessageModal && (
        <CatalogMessageModal
          subject="Mercados"
          onClose={() => setShowMessageModal(false)}
        />
      )}

      {/* Modal de configuración de mercados visibles */}
      {configOpen && (
        <MarketsConfigModal
          allMarkets={marketsList}
          hiddenMarkets={hiddenMarkets}
          onSave={handleConfigSave}
          onClose={() => setConfigOpen(false)}
          t={t}
        />
      )}
    </div>
  )
}
