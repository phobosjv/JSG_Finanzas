import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })
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
function TargetCell({ sec, onUpdate }) {
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
    } catch { /* silencioso — el valor no cambia */ }
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
        ? fmt(sec.target_buy_price)
        : <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>— editar</span>}
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

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Valor</th>
            <th>ISIN</th>
            <th>Google</th>
            <th className="num">Precio</th>
            <th className="num">Var. día</th>
            <th className="num">Mín 1a</th>
            <th className="num">Mín 2a</th>
            <th className="num">Mín 5a</th>
            <th>Alerta</th>
            <th className="num">Dividendo</th>
            <th className="num">Obj. Compra</th>
            <th className="num">% Obj.</th>
            <th style={{ textAlign: 'center' }}>Acción</th>
          </tr>
        </thead>
        <tbody>
          {securities.map(sec => {
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
                {/* Valor */}
                <td>
                  <div className="ticker">{sec.yahoo_ticker}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{sec.name}</div>
                </td>

                {/* ISIN */}
                <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                  {sec.isin ?? '—'}
                </td>

                {/* Google ticker */}
                <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                  {sec.google_ticker ?? '—'}
                </td>

                {/* Precio */}
                <td className="num">
                  {fmt(sec.last_price)}
                  <small style={{ color: 'var(--text-muted)', marginLeft: 3 }}>{sec.currency}</small>
                </td>

                {/* Variación día */}
                <td className={`num ${pctCls}`}>
                  {pct != null ? `${pct >= 0 ? '+' : ''}${fmt(pct)}%` : '—'}
                </td>

                {/* Mín 1a */}
                <td className="num">{fmt(sec.min_1y)}</td>

                {/* Mín 2a */}
                <td className="num">{fmt(sec.min_2y)}</td>

                {/* Mín 5a */}
                <td className="num">{fmt(sec.min_5y)}</td>

                {/* Indicador mínimo naranja */}
                <td>
                  <MinBadge
                    price={sec.last_price}
                    min1y={sec.min_1y}
                    min2y={sec.min_2y}
                    min5y={sec.min_5y}
                  />
                </td>

                {/* Dividendo */}
                <td className="num">{fmt(sec.last_dividend)}</td>

                {/* Precio objetivo compra — editable */}
                <TargetCell sec={sec} onUpdate={onTargetUpdate} />

                {/* % hasta objetivo */}
                <td className={`num ${pctToTarget == null ? 'neu' : pctToTarget > 0 ? 'neg' : 'pos'}`}>
                  {pctToTarget != null
                    ? `${pctToTarget >= 0 ? '+' : ''}${fmt(pctToTarget)}%`
                    : '—'}
                </td>

                {/* Acción: estrella / papelera + alerta comprar */}
                <td style={{ textAlign: 'center', whiteSpace: 'nowrap' }} onClick={e => e.stopPropagation()}>
                  {isBuyAlert && <div className="alert-buy">¡Comprar!</div>}
                  <button
                    className="btn-ghost btn-sm"
                    style={{ padding: '2px 8px', fontSize: '1rem' }}
                    title={sec.is_favorite ? (favoritesTab ? 'Quitar favorito' : 'Quitar favorito') : 'Añadir favorito'}
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
