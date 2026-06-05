import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'
import { useSortableData, SortableHead } from '../hooks/useSortableData'

/**
 * Formateador de precio adaptativo.
 * Activos como Bitcoin muestran 2 dec; micro-caps de crypto usan más.
 */
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

/** Tipo de activo: usa market_type explícito si existe; si no, heurística. */
function assetTypeKey(marketCode, isFund, marketType) {
  if (marketType) return marketType
  if (isFund) return 'fund'
  const c = (marketCode ?? '').toLowerCase()
  if (c.includes('etf'))    return 'etf'
  if (c.includes('crypto')) return 'crypto'
  return 'stock'
}

/** Badge de tipo de activo (ETF / Crypto / Fondo / Acción). */
function AssetBadge({ market, isFund, marketType, t }) {
  const type = assetTypeKey(market, isFund, marketType)
  const key  = `badge.${type}`
  return (
    <span className={`badge-asset ${type}`}>{t(key)}</span>
  )
}

/** Badge naranja cuando el precio actual está en mínimo histórico. */
function MinBadge({ price, min1y, min2y, min5y }) {
  if (price == null) return null
  const p = Number(price)
  let label = null
  if (min5y != null && p <= Number(min5y)) label = 'Mín 5a'
  else if (min2y != null && p <= Number(min2y)) label = 'Mín 2a'
  else if (min1y != null && p <= Number(min1y)) label = 'Mín 1a'
  if (!label) return null
  return <span className="badge-min">{label}</span>
}

/** Celda con precio objetivo editable en línea (solo para favoritos). */
function TargetCell({ sec, onUpdate, t }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(
    sec.target_buy_price != null ? String(sec.target_buy_price) : ''
  )

  if (!sec.is_favorite) return <td className="num" style={{ color: 'var(--text-muted)' }}>—</td>

  async function save() {
    setEditing(false)
    const num = val.trim() === '' ? null : Number(val)
    try {
      await api.patch(`/favorites/${sec.id}`, { target_buy_price: num })
      onUpdate(sec.id, num)
    } catch { /* silencioso */ }
  }

  if (editing) {
    return (
      <td className="num" onClick={e => e.stopPropagation()}>
        <input
          className="target-input"
          type="number"
          step="any"
          value={val}
          autoFocus
          onChange={e => setVal(e.target.value)}
          onBlur={save}
          onKeyDown={e => {
            if (e.key === 'Enter') save()
            if (e.key === 'Escape') setEditing(false)
          }}
        />
      </td>
    )
  }

  const hasTarget = sec.target_buy_price != null
  return (
    <td
      className="num"
      style={{ cursor: 'pointer' }}
      title="Clic para editar"
      onClick={e => { e.stopPropagation(); setEditing(true) }}
    >
      {hasTarget
        ? fmtPrice(sec.target_buy_price)
        : <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{t('common.edit')}</span>}
    </td>
  )
}

/**
 * Tabla de valores del explorador de mercados.
 *
 * Props:
 *   securities  — lista de SecurityOverview del endpoint /markets/overview
 *   favoritesTab — boolean: si true muestra papelera en lugar de estrella
 *   onToggleFav(secId, currentIsFav) — callback al pulsar ★/🗑
 *   onTargetUpdate(secId, newPrice)  — callback al guardar precio objetivo
 */
export default function SecurityTable({ securities, favoritesTab = false, onToggleFav, onTargetUpdate }) {
  const navigate = useNavigate()
  const { t } = useAppConfig()

  // Columnas condicionales: solo se muestran si algún valor del set las tiene
  const hasIsin     = securities.some(s => s.isin != null && s.isin !== '')
  const hasGoogle   = securities.some(s => s.google_ticker != null && s.google_ticker !== '')
  const hasDividend = securities.some(s => s.last_dividend != null)

  const scrollStyle = securities.length > 10 ? { maxHeight: 540, overflowY: 'auto' } : {}

  const numN = v => (v != null && v !== '' ? Number(v) : null)
  const pctToTargetOf = sec => (sec.is_favorite && sec.target_buy_price != null && sec.last_price != null)
    ? (Number(sec.target_buy_price) - Number(sec.last_price)) / Number(sec.last_price) * 100
    : null
  const columns = [
    { key: 'name',   label: t('markets.col_name'),   accessor: s => s.name },
    hasIsin   && { key: 'isin',   label: t('markets.col_isin'),   accessor: s => s.isin || null },
    hasGoogle && { key: 'google', label: t('markets.col_google'), accessor: s => s.google_ticker || null },
    { key: 'price',  label: t('markets.col_price'),  className: 'num', accessor: s => numN(s.last_price) },
    { key: 'change', label: t('markets.col_change'), className: 'num', accessor: s => numN(s.daily_change_pct) },
    { key: 'min1y',  label: t('markets.col_min1y'),  className: 'num', accessor: s => numN(s.min_1y) },
    { key: 'min2y',  label: t('markets.col_min2y'),  className: 'num', accessor: s => numN(s.min_2y) },
    { key: 'min5y',  label: t('markets.col_min5y'),  className: 'num', accessor: s => numN(s.min_5y) },
    { key: 'alert',  label: t('markets.col_alert') },
    hasDividend && { key: 'dividend', label: t('markets.col_dividend'), className: 'num', accessor: s => numN(s.last_dividend) },
    { key: 'target',    label: t('markets.col_target'),     className: 'num', accessor: s => numN(s.target_buy_price) },
    { key: 'targetpct', label: t('markets.col_target_pct'), className: 'num', accessor: pctToTargetOf },
    { key: 'action',    label: t('markets.col_action'), style: { textAlign: 'center' } },
  ].filter(Boolean)

  const { sorted, sortKey, sortDir, requestSort } = useSortableData(securities)

  return (
    <div className="table-wrap" style={scrollStyle}>
      <table>
        <SortableHead columns={columns} sortKey={sortKey} sortDir={sortDir} requestSort={requestSort} />
        <tbody>
          {sorted.map(sec => {
            const pct = sec.daily_change_pct != null ? Number(sec.daily_change_pct) : null
            const pctCls = pct == null ? 'neu' : pct > 0 ? 'pos' : pct < 0 ? 'neg' : 'neu'

            const isBuyAlert = sec.is_favorite
              && sec.target_buy_price != null
              && sec.last_price != null
              && Number(sec.last_price) <= Number(sec.target_buy_price)

            const pctToTarget = sec.is_favorite && sec.target_buy_price != null && sec.last_price != null
              ? ((Number(sec.target_buy_price) - Number(sec.last_price)) / Number(sec.last_price) * 100)
              : null

            return (
              <tr
                key={sec.id}
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/securities/${sec.id}`)}
              >
                {/* Valor + badge tipo activo */}
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
                    <span className="ticker">{sec.yahoo_ticker}</span>
                    <AssetBadge market={sec.market} isFund={sec.is_fund_market} marketType={sec.market_type} t={t} />
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{sec.name}</div>
                </td>

                {/* ISIN (condicional) */}
                {hasIsin && (
                  <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                    {sec.isin ?? '—'}
                  </td>
                )}

                {/* Google ticker (condicional) */}
                {hasGoogle && (
                  <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                    {sec.google_ticker ?? '—'}
                  </td>
                )}

                {/* Precio */}
                <td className="num">
                  {fmtPrice(sec.last_price)}
                  <small style={{ color: 'var(--text-muted)', marginLeft: 3 }}>{sec.currency}</small>
                </td>

                {/* Variación día */}
                <td className={`num ${pctCls}`}>
                  {pct != null ? `${pct >= 0 ? '+' : ''}${fmt(pct)}%` : '—'}
                </td>

                {/* Mín 1a */}
                <td className="num">{fmtPrice(sec.min_1y)}</td>

                {/* Mín 2a */}
                <td className="num">{fmtPrice(sec.min_2y)}</td>

                {/* Mín 5a */}
                <td className="num">{fmtPrice(sec.min_5y)}</td>

                {/* Indicador mínimo naranja */}
                <td>
                  <MinBadge
                    price={sec.last_price}
                    min1y={sec.min_1y}
                    min2y={sec.min_2y}
                    min5y={sec.min_5y}
                  />
                </td>

                {/* Dividendo (condicional) */}
                {hasDividend && (
                  <td className="num">{fmt(sec.last_dividend)}</td>
                )}

                {/* Precio objetivo compra — editable */}
                <TargetCell sec={sec} onUpdate={onTargetUpdate} t={t} />

                {/* % hasta objetivo — color neutro (blanco), no semántico */}
                <td className="num">
                  {pctToTarget != null
                    ? `${pctToTarget >= 0 ? '+' : ''}${fmt(pctToTarget)}%`
                    : '—'}
                </td>

                {/* Acción: estrella / papelera + alerta comprar */}
                <td style={{ textAlign: 'center', whiteSpace: 'nowrap' }} onClick={e => e.stopPropagation()}>
                  {isBuyAlert && <div className="alert-buy">{t('markets.buy_alert')}</div>}
                  <button
                    className="btn-ghost btn-sm"
                    style={{ padding: '2px 8px', fontSize: '1rem' }}
                    title={sec.is_favorite ? t('markets.remove_fav') : t('markets.add_fav')}
                    onClick={() => onToggleFav(sec.id, sec.is_favorite)}
                  >
                    {sec.is_favorite ? (favoritesTab ? '🗑' : '★') : '☆'}
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
