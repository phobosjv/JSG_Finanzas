import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'
import './SecurityCard.css'

/** Formateador de precio adaptativo (igual que en SecurityTable). */
function fmtPrice(val) {
  if (val == null) return '—'
  const n = Number(val)
  let dec = 2
  if (n !== 0 && Math.abs(n) < 0.01) dec = 6
  else if (Math.abs(n) < 1)          dec = 4
  return n.toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })
}

function assetTypeKey(marketCode, isFund, marketType) {
  if (marketType) return marketType
  if (isFund) return 'fund'
  const c = (marketCode ?? '').toLowerCase()
  if (c.includes('etf'))    return 'etf'
  if (c.includes('crypto')) return 'crypto'
  return 'stock'
}

function AssetBadge({ market, isFund, marketType, t }) {
  const type = assetTypeKey(market, isFund, marketType)
  return (
    <span className={`badge-asset ${type}`}>{t(`badge.${type}`)}</span>
  )
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
  const { t } = useAppConfig()

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
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4 }}>
            <span className="ticker">{sec.yahoo_ticker}</span>
            <AssetBadge market={sec.market} isFund={sec.is_fund_market} marketType={sec.market_type} t={t} />
          </div>
          <div className="sec-name">{sec.name}</div>
          {badge && <span className="badge-min" style={{ marginTop: 2 }}>{badge}</span>}
        </div>
        <div className="sec-card-right">
          <div className="sec-price">{fmtPrice(sec.last_price)} <small>{sec.currency}</small></div>
          <div className={`sec-change ${pctCls}`}>
            {pct != null ? `${sign}${fmt(pct)}%` : '—'}
          </div>
          {isBuyAlert && <div className="alert-buy">{t('markets.buy_alert')}</div>}
        </div>
        <span className="sec-chevron">{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className="sec-card-body">
          {sec.isin && (
            <div className="sec-stat-row">
              <span>{t('markets.col_isin')}</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: '0.78rem' }}>{sec.isin}</span>
            </div>
          )}
          {sec.google_ticker && (
            <div className="sec-stat-row">
              <span>{t('markets.col_google')}</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: '0.78rem' }}>{sec.google_ticker}</span>
            </div>
          )}
          <div className="sec-stat-row">
            <span>{t('markets.col_min1y')}</span><span className="num">{fmtPrice(sec.min_1y)}</span>
          </div>
          <div className="sec-stat-row">
            <span>{t('markets.col_min2y')}</span><span className="num">{fmtPrice(sec.min_2y)}</span>
          </div>
          <div className="sec-stat-row">
            <span>{t('markets.col_min5y')}</span><span className="num">{fmtPrice(sec.min_5y)}</span>
          </div>
          <div className="sec-stat-row">
            <span>Máx. 1a</span><span className="num">{fmtPrice(sec.max_1y)}</span>
          </div>
          {sec.last_dividend != null && (
            <div className="sec-stat-row">
              <span>{t('markets.col_dividend')}</span><span className="num">{fmt(sec.last_dividend)}</span>
            </div>
          )}

          {sec.is_favorite && (
            <>
              <div className="sec-stat-row">
                <span>{t('markets.col_target')}</span>
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
                    {sec.target_buy_price != null ? fmtPrice(sec.target_buy_price) : t('common.edit')}
                  </span>
                )}
              </div>
              {pctToTarget != null && (
                <div className="sec-stat-row">
                  <span>{t('markets.col_target_pct')}</span>
                  <span className="num">
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
                {sec.is_favorite
                  ? (favoritesTab ? `🗑 ${t('markets.remove_fav')}` : `★ ${t('markets.remove_fav')}`)
                  : `☆ ${t('markets.add_fav')}`}
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
