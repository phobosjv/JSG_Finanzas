import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  PieChart, Pie, Cell, Tooltip as ReTooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import { api } from '../api/client'

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

function sign(val) { return Number(val) >= 0 ? '+' : '' }
function cls(val)  { return Number(val) > 0 ? 'pos' : Number(val) < 0 ? 'neg' : 'neu' }

function Card({ label, value, sub, clsName }) {
  return (
    <div className="card small">
      <div className={`value ${clsName ?? ''}`}>{value}</div>
      {sub && <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>{sub}</div>}
      <div className="label">{label}</div>
    </div>
  )
}

const DONUT_COLORS = [
  '#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981',
  '#3b82f6', '#f97316', '#14b8a6', '#eab308', '#06b6d4',
]

function shadeHex(hex, pct) {
  const n = parseInt(hex.slice(1), 16)
  const a = Math.round(2.55 * pct)
  const r = Math.max(0, Math.min(255, (n >> 16) + a))
  const g = Math.max(0, Math.min(255, ((n >> 8) & 0xff) + a))
  const b = Math.max(0, Math.min(255, (n & 0xff) + a))
  return '#' + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)
}

function Bar3D({ x, y, width, height, value }) {
  if (!height || !width || Math.abs(height) < 2) return null
  const isPos = Number(value) >= 0
  const front = isPos ? '#22c55e' : '#ef4444'
  const top   = isPos ? '#4ade80' : '#fca5a5'
  const side  = isPos ? '#15803d' : '#b91c1c'
  const d     = Math.max(3, Math.min(width * 0.22, 9))

  if (isPos) {
    return (
      <g>
        <path d={`M${x+width},${y} L${x+width+d},${y-d} L${x+width+d},${y+height-d} L${x+width},${y+height} Z`} fill={side} />
        <path d={`M${x},${y} L${x+d},${y-d} L${x+width+d},${y-d} L${x+width},${y} Z`} fill={top} />
        <rect x={x} y={y} width={width} height={height} fill={front} />
      </g>
    )
  }
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={front} />
      <path d={`M${x+width},${y} L${x+width+d},${y-d} L${x+width+d},${y+height-d} L${x+width},${y+height} Z`} fill={side} />
      <path d={`M${x},${y+height} L${x+d},${y+height-d} L${x+width+d},${y+height-d} L${x+width},${y+height} Z`} fill={shadeHex(front, -20)} />
    </g>
  )
}

/** Celda de precio objetivo de venta editable en línea. */
function TargetSellCell({ pos, onUpdate }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(pos.target_sell_price != null ? String(pos.target_sell_price) : '')

  async function save() {
    setEditing(false)
    const num = val.trim() === '' ? null : Number(val)
    try {
      await api.patch(`/portfolio/${pos.position_id}/target-sell`, { target_sell_price: num })
      onUpdate(pos.position_id, num)
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
          onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }}
        />
      </td>
    )
  }

  return (
    <td
      className="num"
      style={{ cursor: 'pointer' }}
      title="Clic para editar"
      onClick={e => { e.stopPropagation(); setEditing(true) }}
    >
      {pos.target_sell_price != null
        ? <>
            {fmt(pos.target_sell_price)}
            {pos.currency === 'USD' && (
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: 3 }}>$</span>
            )}
          </>
        : <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>— editar</span>}
    </td>
  )
}

export default function Portfolio() {
  const [positions, setPositions]   = useState(null)
  const [closed, setClosed]         = useState([])
  const [error, setError]           = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([api.get('/portfolio'), api.get('/portfolio/closed')])
      .then(([open, cls]) => { setPositions(open); setClosed(cls) })
      .catch(err => setError(err.message))
  }, [])

  function handleTargetUpdate(positionId, newPrice) {
    setPositions(prev =>
      prev.map(p => p.position_id === positionId ? { ...p, target_sell_price: newPrice } : p)
    )
  }

  if (error)     return <div className="state-error">{error}</div>
  if (!positions) return <div className="state-loading"><div className="spinner" /></div>

  // Totales de posiciones abiertas
  const totalValue     = positions.reduce((s, p) => s + Number(p.market_value_eur), 0)
  const totalCost      = positions.reduce((s, p) => s + Number(p.cost_eur), 0)
  const totalPnL       = positions.reduce((s, p) => s + Number(p.unrealized_pnl_eur), 0)
  const totalDivs      = positions.reduce((s, p) => s + Number(p.dividends_eur), 0)
                       + closed.reduce((s, p) => s + Number(p.dividends_eur), 0)
  const totalDayEur    = positions.reduce((s, p) => s + (p.daily_change_eur != null ? Number(p.daily_change_eur) : 0), 0)
  const realizedTotal  = closed.reduce((s, p) => s + Number(p.realized_pnl_eur), 0)

  // Beneficio total histórico: latente + realizado (parciales y cerradas) + dividendos
  const totalHistorical = positions.reduce(
    (s, p) => s + Number(p.unrealized_pnl_eur) + Number(p.realized_pnl_eur) + Number(p.dividends_eur), 0
  ) + closed.reduce((s, p) => s + Number(p.total_profit_eur), 0)
  return (
    <div>
      <h1>Mi cartera</h1>

      {/* Tarjetas resumen */}
      <div className="card-row">
        <Card
          label="Beneficio total histórico"
          value={`${sign(totalHistorical)}${fmt(totalHistorical)} €`}
          clsName={cls(totalHistorical)}
        />
        <Card label="Importe invertido"  value={`${fmt(totalCost)} €`} />
        <Card label="Valor actual"       value={`${fmt(totalValue)} €`} />
        <Card
          label="B/P latente"
          value={`${sign(totalPnL)}${fmt(totalPnL)} €`}
          clsName={cls(totalPnL)}
        />
        <Card
          label="Dividendos cobrados"
          value={`${fmt(totalDivs)} €`}
        />
        <Card
          label="Var. hoy"
          value={`${sign(totalDayEur)}${fmt(totalDayEur)} €`}
          clsName={cls(totalDayEur)}
        />
        {realizedTotal !== 0 && (
          <Card
            label="Beneficio realizado"
            value={`${sign(realizedTotal)}${fmt(realizedTotal)} €`}
            clsName={cls(realizedTotal)}
          />
        )}
      </div>

      {/* Gráficos — solo si hay posiciones abiertas */}
      {positions.length > 0 && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>

          {/* Donut 3D: distribución de cartera */}
          <div className="card" style={{ flex: '1 1 340px', minWidth: 0 }}>
            <h2>Distribución de cartera</h2>
            <div style={{ position: 'relative' }}>
              {/* Sombra elíptica debajo del donut */}
              <div style={{
                position: 'absolute', bottom: 4, left: '50%',
                transform: 'translateX(-50%)',
                width: '52%', height: 18,
                background: 'rgba(0,0,0,0.45)',
                borderRadius: '50%',
                filter: 'blur(10px)',
                pointerEvents: 'none',
              }} />
              <div style={{
                transform: 'perspective(520px) rotateX(22deg)',
                transformOrigin: 'center 68%',
                filter: 'drop-shadow(0 14px 18px rgba(0,0,0,0.55))',
              }}>
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={positions.map(p => ({
                        name: p.yahoo_ticker,
                        value: Number(p.market_value_eur),
                      }))}
                      cx="50%"
                      cy="52%"
                      innerRadius="46%"
                      outerRadius="72%"
                      dataKey="value"
                      paddingAngle={3}
                      strokeWidth={0}
                    >
                      {positions.map((_, i) => {
                        const base = DONUT_COLORS[i % DONUT_COLORS.length]
                        return (
                          <Cell
                            key={i}
                            fill={base}
                            stroke={shadeHex(base, -30)}
                            strokeWidth={1.5}
                          />
                        )
                      })}
                    </Pie>
                    <ReTooltip
                      contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: '0.82rem' }}
                      formatter={(value, name) => [
                        `${fmt(value)} € (${totalValue > 0 ? fmt(value / totalValue * 100) : '0'}%)`,
                        name,
                      ]}
                    />
                    <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '0.78rem' }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Barras 3D: % B/P por acción */}
          <div className="card" style={{ flex: '2 1 420px', minWidth: 0 }}>
            <h2>Beneficio / Pérdida por acción (%)</h2>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={[...positions]
                  .sort((a, b) => Number(b.unrealized_pnl_pct) - Number(a.unrealized_pnl_pct))
                  .map(p => ({
                    name: p.yahoo_ticker,
                    pct: Number(p.unrealized_pnl_pct),
                    value: Number(p.unrealized_pnl_pct),
                  }))}
                margin={{ top: 16, right: 20, left: 8, bottom: 4 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                <YAxis
                  tickFormatter={v => `${v}%`}
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  width={50}
                />
                <ReTooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: '0.82rem' }}
                  formatter={v => [`${sign(v)}${fmt(v)}%`, 'B/P']}
                />
                <Bar dataKey="pct" shape={<Bar3D />} isAnimationActive={true} />
              </BarChart>
            </ResponsiveContainer>
          </div>

        </div>
      )}

      {/* Tabla posiciones abiertas */}
      {positions.length === 0 ? (
        <div className="state-empty">No hay posiciones abiertas</div>
      ) : (
        <div className="card">
          <h2>Posiciones abiertas</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Valor</th>
                  <th className="num">Acciones</th>
                  <th className="num">P. medio</th>
                  <th className="num">Invertido</th>
                  <th className="num">Precio act.</th>
                  <th className="num">Valor act.</th>
                  <th className="num">B/P €</th>
                  <th className="num">B/P %</th>
                  <th className="num">Var. hoy €</th>
                  <th className="num">Var. hoy %</th>
                  <th className="num">Dividendos</th>
                  <th className="num">Total B/P</th>
                  <th className="num">Máx. 1a</th>
                  <th className="num">Obj. Venta</th>
                  <th className="num">% Obj.</th>
                  <th style={{ textAlign: 'center' }}>Alerta</th>
                </tr>
              </thead>
              <tbody>
                {positions.map(p => {
                  const isSellAlert = p.target_sell_price != null
                    && p.current_price != null
                    && Number(p.current_price) >= Number(p.target_sell_price)

                  const pctToSell = p.target_sell_price != null && p.current_price != null
                    ? (Number(p.target_sell_price) - Number(p.current_price)) / Number(p.current_price) * 100
                    : null

                  return (
                    <tr
                      key={p.position_id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => navigate(`/securities/${p.security_id}`)}
                    >
                      <td>
                        <div className="ticker">{p.yahoo_ticker}</div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{p.name}</div>
                      </td>
                      <td className="num">{fmt(p.shares, 4)}</td>
                      <td className="num">{fmt(p.avg_cost_eur)}</td>
                      <td className="num">{fmt(p.cost_eur)}</td>
                      <td className="num">
                        {fmt(p.current_price)}
                        {p.currency === 'USD' && p.current_price != null && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: 3 }}>$</span>
                        )}
                      </td>
                      <td className="num">{fmt(p.market_value_eur)}</td>
                      <td className={`num ${cls(p.unrealized_pnl_eur)}`}>
                        {sign(p.unrealized_pnl_eur)}{fmt(p.unrealized_pnl_eur)}
                      </td>
                      <td className={`num ${cls(p.unrealized_pnl_pct)}`}>
                        {sign(p.unrealized_pnl_pct)}{fmt(p.unrealized_pnl_pct)}%
                      </td>
                      <td className={`num ${p.daily_change_eur != null ? cls(p.daily_change_eur) : 'neu'}`}>
                        {p.daily_change_eur != null ? `${sign(p.daily_change_eur)}${fmt(p.daily_change_eur)}` : '—'}
                      </td>
                      <td className={`num ${p.daily_change_pct != null ? cls(p.daily_change_pct) : 'neu'}`}>
                        {p.daily_change_pct != null ? `${sign(p.daily_change_pct)}${fmt(p.daily_change_pct)}%` : '—'}
                      </td>
                      <td className="num">{fmt(p.dividends_eur)}</td>
                      <td className={`num ${cls(p.total_profit_eur)}`}>
                        {sign(p.total_profit_eur)}{fmt(p.total_profit_eur)}
                      </td>
                      <td className="num">
                        {fmt(p.max_1y)}
                        {p.currency === 'USD' && p.max_1y != null && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: 3 }}>$</span>
                        )}
                      </td>
                      <TargetSellCell pos={p} onUpdate={handleTargetUpdate} />
                      <td className={`num ${pctToSell == null ? 'neu' : pctToSell > 0 ? 'neg' : 'pos'}`}>
                        {pctToSell != null ? `${sign(pctToSell)}${fmt(pctToSell)}%` : '—'}
                      </td>
                      <td style={{ textAlign: 'center' }} onClick={e => e.stopPropagation()}>
                        {isSellAlert && <span className="alert-buy" style={{ color: 'var(--green)' }}>¡Vender!</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tabla posiciones cerradas */}
      {closed.length > 0 && (
        <div className="card">
          <h2>Posiciones cerradas</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Valor</th>
                  <th className="num">Acciones</th>
                  <th className="num">Coste €</th>
                  <th className="num">Ingresos €</th>
                  <th className="num">B/P realizado</th>
                  <th className="num">Dividendos</th>
                  <th className="num">Total B/P</th>
                </tr>
              </thead>
              <tbody>
                {closed.map(p => (
                  <tr
                    key={p.position_id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/securities/${p.security_id}`)}
                  >
                    <td>
                      <div className="ticker">{p.yahoo_ticker}</div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{p.name}</div>
                    </td>
                    <td className="num">{fmt(p.shares_sold, 4)}</td>
                    <td className="num">{fmt(p.cost_eur)}</td>
                    <td className="num">{fmt(p.proceeds_eur)}</td>
                    <td className={`num ${cls(p.realized_pnl_eur)}`}>
                      {sign(p.realized_pnl_eur)}{fmt(p.realized_pnl_eur)}
                    </td>
                    <td className="num">{fmt(p.dividends_eur)}</td>
                    <td className={`num ${cls(p.total_profit_eur)}`}>
                      {sign(p.total_profit_eur)}{fmt(p.total_profit_eur)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
