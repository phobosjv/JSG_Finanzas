import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  PieChart, Pie, Cell, Tooltip as ReTooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  AreaChart, Area,
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
  if (!width || Math.abs(height || 0) < 2) return null
  const isPos = Number(value) >= 0
  const front = isPos ? '#22c55e' : '#ef4444'
  const top   = isPos ? '#4ade80' : '#fca5a5'
  const side  = isPos ? '#15803d' : '#b91c1c'
  const d     = Math.max(3, Math.min(width * 0.22, 9))
  // Recharts pasa height negativo para barras bajo el eje; SVG ignora rect con height<0
  const y0 = Math.min(y, y + height)  // extremo superior en coordenadas de pantalla
  const h  = Math.abs(height)

  // Misma estructura para positivo y negativo: lado → capitel → frontal encima.
  // El capitel (top) se dibuja en la línea del cero para ambos casos.
  return (
    <g>
      <path d={`M${x+width},${y0} L${x+width+d},${y0-d} L${x+width+d},${y0+h-d} L${x+width},${y0+h} Z`} fill={side} />
      <path d={`M${x},${y0} L${x+d},${y0-d} L${x+width+d},${y0-d} L${x+width},${y0} Z`} fill={top} />
      <rect x={x} y={y0} width={width} height={h} fill={front} />
    </g>
  )
}

/** Celda de precio objetivo de venta editable en línea. */
function TargetSellCell({ pos, onUpdate }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(pos.target_sell_price != null ? String(pos.target_sell_price) : '')

  async function save() {
    setEditing(false)
    const trimmed = val.trim()
    if (trimmed === '') {
      try {
        await api.patch(`/portfolio/${pos.position_id}/target-sell`, { target_sell_price: null })
        onUpdate(pos.position_id, null)
      } catch { /* silencioso */ }
      return
    }
    const num = Number(trimmed)
    if (isNaN(num) || num <= 0) return   // valor inválido: ignorar silenciosamente
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
  const [history, setHistory]       = useState([])
  const [histYears, setHistYears]   = useState(2)
  const [error, setError]           = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      api.get('/portfolio'),
      api.get('/portfolio/closed'),
      api.get('/portfolio/history'),
    ])
      .then(([open, cls, hist]) => { setPositions(open); setClosed(cls); setHistory(hist) })
      .catch(err => setError(err.message))
  }, [])

  function handleTargetUpdate(positionId, newPrice) {
    setPositions(prev =>
      prev.map(p => p.position_id === positionId ? { ...p, target_sell_price: newPrice } : p)
    )
  }

  if (error)     return <div className="state-error">{error}</div>
  if (!positions) return <div className="state-loading"><div className="spinner" /></div>

  // Totales
  const totalValue    = positions.reduce((s, p) => s + Number(p.market_value_eur), 0)
  const totalCost     = positions.reduce((s, p) => s + Number(p.cost_eur), 0)
  const totalPnL      = positions.reduce((s, p) => s + Number(p.unrealized_pnl_eur), 0)
  const totalDivs     = positions.reduce((s, p) => s + Number(p.dividends_eur), 0)
                      + closed.reduce((s, p) => s + Number(p.dividends_eur), 0)
  const totalDayEur   = positions.reduce((s, p) => s + (p.daily_change_eur != null ? Number(p.daily_change_eur) : 0), 0)
  const realizedNet   = positions.reduce((s, p) => s + Number(p.realized_pnl_eur), 0)
                      + closed.reduce((s, p) => s + Number(p.realized_pnl_eur), 0)
  const totalFees     = positions.reduce((s, p) => s + Number(p.fees_eur), 0)
                      + closed.reduce((s, p) => s + Number(p.fees_eur), 0)
  // Beneficio ventas sin comisiones: realized neto + comisiones (precios puros)
  const grossRealized = realizedNet + totalFees
  // B/P Total = latente + ventas_bruto + dividendos - comisiones = latente + realized_neto + divs
  const bpTotal       = totalPnL + realizedNet + totalDivs
  return (
    <div>
      <h1>Mi cartera</h1>

      {/* Tarjetas resumen */}
      <div className="card-row">
        <Card label="Importe invertido" value={`${fmt(totalCost)} €`} />
        <Card label="Valor actual"      value={`${fmt(totalValue)} €`} />
        <Card
          label="B/P latente"
          value={`${sign(totalPnL)}${fmt(totalPnL)} €`}
          clsName={cls(totalPnL)}
        />
        <Card
          label="Var. hoy"
          value={`${sign(totalDayEur)}${fmt(totalDayEur)} €`}
          clsName={cls(totalDayEur)}
        />
        <Card
          label="Beneficio ventas"
          value={`${sign(grossRealized)}${fmt(grossRealized)} €`}
          clsName={cls(grossRealized)}
        />
        <Card label="Dividendos cobrados" value={`${fmt(totalDivs)} €`} />
        <Card
          label="Comisiones pagadas"
          value={`-${fmt(totalFees)} €`}
          clsName="neg"
        />
        <Card
          label="Beneficio total"
          value={`${sign(bpTotal)}${fmt(bpTotal)} €`}
          clsName={cls(bpTotal)}
        />
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
                        name: p.name,
                        value: Number(p.market_value_eur),
                        security_id: p.security_id,
                      }))}
                      cx="50%"
                      cy="52%"
                      innerRadius="46%"
                      outerRadius="72%"
                      dataKey="value"
                      paddingAngle={3}
                      strokeWidth={0}
                      style={{ cursor: 'pointer' }}
                      onClick={(data) => data?.security_id && navigate(`/securities/${data.security_id}`)}
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
                      contentStyle={{ background: '#1e1b2e', border: '1px solid #4f46e5', borderRadius: 6, fontSize: '0.82rem', color: '#f1f5f9' }}
                      labelStyle={{ color: '#f1f5f9', fontWeight: 600 }}
                      itemStyle={{ color: '#c4b5fd' }}
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
                    name: p.name,
                    pct: Number(p.unrealized_pnl_pct),
                    value: Number(p.unrealized_pnl_pct),
                    security_id: p.security_id,
                  }))}
                margin={{ top: 16, right: 20, left: 8, bottom: 64 }}
                style={{ cursor: 'pointer' }}
                onClick={(data) => {
                  const id = data?.activePayload?.[0]?.payload?.security_id
                  if (id) navigate(`/securities/${id}`)
                }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fill: 'var(--text-muted)', fontSize: 11, textAnchor: 'end' }}
                  angle={-35}
                  interval={0}
                />
                <YAxis
                  tickFormatter={v => `${v}%`}
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  width={50}
                />
                <ReTooltip
                  contentStyle={{ background: '#1e1b2e', border: '1px solid #4f46e5', borderRadius: 6, fontSize: '0.82rem', color: '#f1f5f9' }}
                  labelStyle={{ color: '#f1f5f9', fontWeight: 600 }}
                  itemStyle={{ color: '#c4b5fd' }}
                  formatter={v => [`${sign(v)}${fmt(v)}%`, 'B/P']}
                />
                <Bar dataKey="pct" shape={<Bar3D />} isAnimationActive={true} />
              </BarChart>
            </ResponsiveContainer>
          </div>

        </div>
      )}

      {/* Gráfico de líneas: evolución del valor de cartera */}
      {history.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <h2 style={{ margin: 0 }}>Evolución del valor de cartera</h2>
            <div style={{ display: 'flex', gap: 4 }}>
              {[1, 2, 5].map(y => (
                <button
                  key={y}
                  onClick={() => setHistYears(y)}
                  style={{
                    padding: '3px 10px',
                    fontSize: '0.78rem',
                    fontWeight: histYears === y ? 700 : 400,
                    borderRadius: 4,
                    border: '1px solid var(--border)',
                    background: histYears === y ? 'var(--primary, #6366f1)' : 'transparent',
                    color: histYears === y ? '#fff' : 'var(--text-muted)',
                    cursor: 'pointer',
                    lineHeight: 1.4,
                  }}
                >{y}A</button>
              ))}
            </div>
          </div>
          {(() => {
            const cutoff = new Date()
            cutoff.setFullYear(cutoff.getFullYear() - histYears)
            const cutStr = cutoff.toISOString().slice(0, 10)
            const filtered = history.filter(p => p.date >= cutStr)
            return (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={filtered} margin={{ top: 8, right: 16, left: 8, bottom: 4 }}>
              <defs>
                <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
                tickFormatter={d => d.slice(5)}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
                tickFormatter={v => `${fmt(v / 1000, 0)}k`}
                width={44}
              />
              <ReTooltip
                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6, fontSize: '0.82rem' }}
                formatter={v => [`${fmt(v)} €`, 'Valor cartera']}
                labelFormatter={d => d}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#6366f1"
                strokeWidth={2}
                fill="url(#portfolioGrad)"
                dot={false}
                activeDot={{ r: 4, fill: '#6366f1' }}
              />
            </AreaChart>
          </ResponsiveContainer>
            )
          })()}
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
