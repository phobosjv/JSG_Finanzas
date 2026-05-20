import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import './SecurityCard.css'

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })
}

function minLabel(price, min1y, min2y, min5y) {
  if (price == null) return null
  const p = Number(price)
  if (min5y != null && p <= Number(min5y)) return 'Mín 5a'
  if (min2y != null && p <= Number(min2y)) return 'Mín 2a'
  if (min1y != null && p <= Number(min1y)) return 'Mín 1a'
  return null
}

/**
 * Tarjeta desplegable para móvil.
 * Props: sec (SecurityOverview), favoritesTab, onToggleFav, onTargetUpdate
 */
export default function SecurityCard({ sec, favoritesTab = false, onToggleFav, onTargetUpdate }) {
  const [open, setOpen]         = useState(false)
  const [editTarget, setEdit]   = useState(false)
  const [targetVal, setTargetV] = useState(
    sec.target_buy_price != null ? String(sec.target_buy_price) : ''
  )
  const navigate = useNavigate()

  const pct    = sec.daily_change_pct != null ? Number(sec.daily_change_pct) : null
  const pctCls = pct == null ? 'neu' : pct > 0 ? 'pos' : pct < 0 ? 'neg' : 'neu'
  const sign   = pct != null && pct > 0 ? '+' : ''
  const badge  = minLabel(sec.last_price, sec.min_1y, sec.min_2y, sec.min_5y)

  const isBuyAlert = sec.is_favorite
    && sec.target_buy_price != null
    && sec.last_price != null
    && Number(sec.last_price) <= Number(sec.target_buy_price)

  const pctToTarget = sec.is_favorite && sec.target_buy_price != null && sec.last_price != null
    ? ((Number(sec.target_buy_price) - Number(sec.last_price)) / Number(sec.last_price) * 100)
    : null

  async function saveTarget() {
    setEdit(false)
    const num = targetVal.trim() === '' ? null : Number(targetVal)
    try {
      await api.patch(`/favorites/${sec.id}`, { target_buy_price: num })
      onTargetUpdate?.(sec.id, num)
    } catch { /* silencioso */ }
  }

  return (
    <div className="sec-card card">
      <div className="sec-card-header" onClick={() => setOpen(o => !o)}>
        <div>
          <div className="ticker">{sec.yahoo_ticker}</div>
          <div className="sec-name">{sec.name}</div>
          {badge && <span className="badge-min" style={{ marginTop: 2 }}>{badge}</span>}
        </div>
        <div className="sec-card-right">
          <div className="sec-price">{fmt(sec.last_price)} <small>{sec.currency}</small></div>
          <div className={`sec-change ${pctCls}`}>
            {pct != null ? `${sign}${fmt(pct)}%` : '—'}
          </div>
          {isBuyAlert && <div className="alert-buy">¡Comprar!</div>}
        </div>
        <span className="sec-chevron">{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className="sec-card-body">
          {sec.isin && (
            <div className="sec-stat-row">
              <span>ISIN</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: '0.78rem' }}>{sec.isin}</span>
            </div>
          )}
          {sec.google_ticker && (
            <div className="sec-stat-row">
              <span>Google</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: '0.78rem' }}>{sec.google_ticker}</span>
            </div>
          )}
          <div className="sec-stat-row">
            <span>Mín. 1a</span><span className="num">{fmt(sec.min_1y)}</span>
          </div>
          <div className="sec-stat-row">
            <span>Mín. 2a</span><span className="num">{fmt(sec.min_2y)}</span>
          </div>
          <div className="sec-stat-row">
            <span>Mín. 5a</span><span className="num">{fmt(sec.min_5y)}</span>
          </div>
          <div className="sec-stat-row">
            <span>Máx. 1a</span><span className="num">{fmt(sec.max_1y)}</span>
          </div>
          <div className="sec-stat-row">
            <span>Dividendo</span><span className="num">{fmt(sec.last_dividend)}</span>
          </div>

          {sec.is_favorite && (
            <>
              <div className="sec-stat-row">
                <span>Obj. Compra</span>
                {editTarget ? (
                  <input
                    type="number"
                    step="any"
                    value={targetVal}
                    autoFocus
                    className="target-input"
                    onChange={e => setTargetV(e.target.value)}
                    onBlur={saveTarget}
                    onKeyDown={e => { if (e.key === 'Enter') saveTarget() }}
                    onClick={e => e.stopPropagation()}
                  />
                ) : (
                  <span
                    className="num"
                    style={{ cursor: 'pointer', textDecoration: 'underline dotted' }}
                    onClick={e => { e.stopPropagation(); setEdit(true) }}
                  >
                    {sec.target_buy_price != null ? fmt(sec.target_buy_price) : '— editar'}
                  </span>
                )}
              </div>
              {pctToTarget != null && (
                <div className="sec-stat-row">
                  <span>% hasta obj.</span>
                  <span className={`num ${pctToTarget > 0 ? 'neg' : 'pos'}`}>
                    {pctToTarget >= 0 ? '+' : ''}{fmt(pctToTarget)}%
                  </span>
                </div>
              )}
            </>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            {onToggleFav && (
              <button
                className="btn-ghost btn-sm"
                onClick={e => { e.stopPropagation(); onToggleFav(sec.id, sec.is_favorite) }}
              >
                {sec.is_favorite ? (favoritesTab ? '🗑 Quitar' : '★ Favorito') : '☆ Favorito'}
              </button>
            )}
            <button
              className="btn-ghost btn-sm"
              style={{ flex: 1 }}
              onClick={e => { e.stopPropagation(); navigate(`/securities/${sec.id}`) }}
            >
              Ver detalle →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
