/**
 * PortfolioChartsPanel.jsx
 * ========================
 * Componente reutilizable con los tres gráficos de cartera.
 * Usado tanto en Portfolio.jsx (sección completa) como en Dashboard.jsx
 * (sección opcional configurable).
 *
 * Props:
 *   positions     — array de posiciones abiertas (mismo shape que /api/portfolio)
 *   history       — array de puntos históricos   (mismo shape que /api/portfolio/history)
 *   chartsVisible — array de ids a mostrar: 'distribution' | 'pnl_pct' | 'history'
 *   t             — función de traducción (de useAppConfig)
 *   navigate      — función de React Router (useNavigate)
 */

import { useState } from 'react'
import {
  PieChart, Pie, Cell, Tooltip as ReTooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  AreaChart, Area,
  ScatterChart, Scatter, ZAxis,
} from 'recharts'

// ─── Colores y utilidades ────────────────────────────────────────────────────

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

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

function sign(val) { return Number(val) >= 0 ? '+' : '' }

// ─── Barra 3D ────────────────────────────────────────────────────────────────

function Bar3D({ x, y, width, height, value }) {
  if (!width || Math.abs(height || 0) < 2) return null
  const isPos = Number(value) >= 0
  const front = isPos ? '#22c55e' : '#ef4444'
  const top   = isPos ? '#4ade80' : '#fca5a5'
  const side  = isPos ? '#15803d' : '#b91c1c'
  const d     = Math.max(3, Math.min(width * 0.22, 9))
  const y0    = Math.min(y, y + height)
  const h     = Math.abs(height)
  return (
    <g>
      <path d={`M${x+width},${y0} L${x+width+d},${y0-d} L${x+width+d},${y0+h-d} L${x+width},${y0+h} Z`} fill={side} />
      <path d={`M${x},${y0} L${x+d},${y0-d} L${x+width+d},${y0-d} L${x+width},${y0} Z`} fill={top} />
      <rect x={x} y={y0} width={width} height={h} fill={front} />
    </g>
  )
}

// ─── Gráfico 1: Donut distribución ──────────────────────────────────────────

export function DistributionChart({ positions, t, navigate }) {
  const totalValue = positions.reduce((s, p) => s + Number(p.market_value_eur), 0)
  return (
    <div className="card" style={{ flex: '1 1 340px', minWidth: 0 }}>
      <h2>{t('portfolio.chart_distribution')}</h2>
      <div style={{ position: 'relative' }}>
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
          <ResponsiveContainer width="100%" height={280}>
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
  )
}

// ─── Gráfico 2: Barras 3D B/P por acción ────────────────────────────────────

export function PnLChart({ positions, t, navigate }) {
  return (
    <div className="card" style={{ flex: '2 1 420px', minWidth: 0 }}>
      <h2>{t('portfolio.chart_pnl_pct')}</h2>
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
  )
}

// ─── Gráfico 3: Área evolución del valor ────────────────────────────────────

export function HistoryChart({ history, t }) {
  const [histYears, setHistYears] = useState(2)
  const cutoff = new Date()
  cutoff.setFullYear(cutoff.getFullYear() - histYears)
  const cutStr  = cutoff.toISOString().slice(0, 10)
  const filtered = history.filter(p => p.date >= cutStr)

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>{t('portfolio.chart_history')}</h2>
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
            formatter={v => [`${fmt(v)} €`, t('portfolio.chart_history_tooltip')]}
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
    </div>
  )
}

// ─── Panel principal exportado ───────────────────────────────────────────────

/**
 * Renderiza los gráficos solicitados en chartsVisible.
 * Los gráficos 'distribution' y 'pnl_pct' aparecen en fila (flex-wrap).
 * El gráfico 'history' ocupa el ancho completo debajo.
 */
export default function PortfolioChartsPanel({ positions, history, chartsVisible, t, navigate }) {
  if (!positions || positions.length === 0) return null

  const showDistrib  = chartsVisible.includes('distribution')
  const showPnl      = chartsVisible.includes('pnl_pct')
  const showHistory  = chartsVisible.includes('history') && history && history.length > 0

  return (
    <div>
      {(showDistrib || showPnl) && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
          {showDistrib && <DistributionChart positions={positions} t={t} navigate={navigate} />}
          {showPnl     && <PnLChart          positions={positions} t={t} navigate={navigate} />}
        </div>
      )}
      {showHistory && <HistoryChart history={history} t={t} />}
    </div>
  )
}

// ─── Utilidad: color por % de rentabilidad + tiempo en cartera ──────────────
//
// Positivos: el color depende de la rentabilidad ANUALIZADA (pct/años).
//   - Muy rentable en poco tiempo (>= 60%/año) → verde intenso.
//   - Poco rentable en mucho tiempo (<= 3%/año) → naranja oscuro (sin llegar a rojo).
// Negativos: siempre rojo, más oscuro cuanto mayor sea la pérdida y más tiempo.
//   - Pérdida pequeña en poco tiempo → rojo claro.
//   - Pérdida grande en mucho tiempo → rojo oscuro.

function lerp(a, b, t) { return Math.round(a + (b - a) * t) }

function pnlColor(pct, days) {
  const d = Number(days) || 0
  const p = Number(pct)  || 0

  if (p < 0) {
    // Intensidad: combinación de magnitud y duración de la pérdida.
    // |pct| en %, years en [0, ∞). intensity ≈ |pct| · (1 + years/3)
    const years = d / 365
    const intensity = Math.abs(p) * (1 + years / 3)
    // Mapeo: 5 → rojo claro, 80+ → rojo oscuro
    const t = Math.max(0, Math.min(1, (intensity - 5) / 75))
    // Rojo claro #fca5a5 → rojo oscuro #7f1d1d
    const r = lerp(252, 127, t)
    const g = lerp(165,  29, t)
    const b = lerp(165,  29, t)
    return `rgb(${r},${g},${b})`
  }

  // Positivo: rentabilidad anualizada.
  // Evita división por cero usando un mínimo de 0.05 años (~18 días).
  const years = Math.max(d / 365, 0.05)
  const annualized = p / years
  // Mapeo: 3%/año → naranja oscuro, 60%/año → verde intenso
  const t = Math.max(0, Math.min(1, (annualized - 3) / 57))
  // Naranja oscuro #cc5500 → verde intenso #16a34a
  const r = lerp(204,  22, t)
  const g = lerp( 85, 163, t)
  const b = lerp(  0,  74, t)
  return `rgb(${r},${g},${b})`
}

function fmtDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

// ─── Scatter posiciones cerradas ─────────────────────────────────────────────

export function ClosedScatterChart({ data, t }) {
  const [logScale, setLogScale] = useState(false)
  if (!data || data.length === 0) return null

  const maxCost = Math.max(...data.map(d => Number(d.cost_eur)), 1)

  const CustomDot = (props) => {
    const { cx, cy, payload } = props
    if (typeof cx !== 'number' || typeof cy !== 'number') return null
    const r = Math.max(6, Math.sqrt(Number(payload.cost_eur) / maxCost) * 24)
    const color = pnlColor(payload.pnl_pct, payload.avg_days_held)
    const label = `${payload.name} - ${fmtDate(payload.last_sell_date)}`
    return (
      <g>
        <circle cx={cx} cy={cy} r={r} fill={color} fillOpacity={0.85} stroke="#fff" strokeWidth={1} />
        <text x={cx} y={cy - r - 4} textAnchor="middle" fontSize={10}
          fill="var(--text-muted)" style={{ pointerEvents: 'none' }}>
          {label}
        </text>
      </g>
    )
  }

  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload?.length) return null
    const d = payload[0].payload
    return (
      <div style={{ background: '#1e1b2e', border: '1px solid #6366f1', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#e2e8f0' }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.name}</div>
        <div>Venta: {fmtDate(d.last_sell_date)}</div>
        <div>Días: {Math.round(d.avg_days_held)}</div>
        <div style={{ color: pnlColor(d.pnl_pct, d.avg_days_held) }}>
          {d.pnl_pct >= 0 ? '+' : ''}{Number(d.pnl_pct).toFixed(2)} %
        </div>
        <div>Resultado: {Number(d.realized_pnl_eur) >= 0 ? '+' : ''}{Number(d.realized_pnl_eur).toFixed(2)} €</div>
        <div style={{ color: 'var(--text-muted)' }}>Capital: {Number(d.cost_eur).toFixed(0)} €</div>
      </div>
    )
  }

  return (
    <div className="card" style={{ marginTop: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <h2 style={{ margin: 0 }}>{t('portfolio.closed_scatter_title')}</h2>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.85rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
          <span>Eje X lineal</span>
          <div
            onClick={() => setLogScale(s => !s)}
            style={{
              width: 40, height: 20, borderRadius: 10, cursor: 'pointer',
              background: logScale ? '#6366f1' : 'var(--border)',
              position: 'relative', transition: 'background 0.2s',
            }}
          >
            <div style={{
              position: 'absolute', top: 2, left: logScale ? 22 : 2,
              width: 16, height: 16, borderRadius: '50%',
              background: '#fff', transition: 'left 0.2s',
            }} />
          </div>
          <span>logarítmico</span>
        </label>
      </div>
      <ResponsiveContainer width="100%" height={340}>
        <ScatterChart margin={{ top: 30, right: 30, bottom: 20, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis
            type="number" dataKey="avg_days_held" name={t('portfolio.closed_scatter_days')}
            scale={logScale ? 'log' : 'auto'}
            domain={logScale ? [1, 'auto'] : ['auto', 'auto']}
            allowDataOverflow={logScale}
            label={{ value: t('portfolio.closed_scatter_days'), position: 'insideBottom', offset: -8, fill: 'var(--text-muted)', fontSize: 12 }}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
            tickFormatter={v => v >= 365 ? `${(v/365).toFixed(1)}a` : `${Math.round(v)}d`}
          />
          <YAxis
            type="number" dataKey="pnl_pct" name={t('portfolio.closed_scatter_pnl')}
            tickFormatter={v => `${v}%`}
            label={{ value: t('portfolio.closed_scatter_pnl'), angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 12 }}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
          />
          <ZAxis type="number" dataKey="cost_eur" range={[40, 900]} />
          <ReTooltip content={<CustomTooltip />} />
          <Scatter data={data} shape={<CustomDot />} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

// ─── Bar chart horizontal — dividendos por acción ────────────────────────────

export function DividendBarChart({ data, t, navigate }) {
  if (!data || data.length === 0) return null

  const sorted = [...data].sort((a, b) => b.total_eur - a.total_eur)
  const chartData = sorted.map(d => ({
    label: d.yahoo_ticker,
    name: d.name,
    value: Number(d.total_eur),
    count: d.count,
    security_id: d.security_id,
  }))

  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload?.length) return null
    const d = payload[0].payload
    return (
      <div style={{ background: '#1e1b2e', border: '1px solid #6366f1', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#e2e8f0' }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.name}</div>
        <div>Total: {d.value.toFixed(2)} €</div>
        <div style={{ color: 'var(--text-muted)' }}>{d.count} cobros</div>
      </div>
    )
  }

  const barH = Math.max(240, chartData.length * 32)

  return (
    <div className="card" style={{ flex: '1 1 320px', minWidth: 0 }}>
      <h3 style={{ marginBottom: 12, fontSize: '1rem' }}>{t('portfolio.div_bar_title')}</h3>
      <ResponsiveContainer width="100%" height={barH}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 40, bottom: 4, left: 8 }}
          style={{ cursor: navigate ? 'pointer' : 'default' }}
          onClick={(e) => {
            const id = e?.activePayload?.[0]?.payload?.security_id
            if (id && navigate) navigate(`/securities/${id}`)
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
          <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} tickFormatter={v => `${v}€`} />
          <YAxis type="category" dataKey="label" width={60} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
          <ReTooltip content={<CustomTooltip />} />
          <Bar dataKey="value" fill="#6366f1" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ─── Scatter yield on cost vs. antigüedad ────────────────────────────────────

export function DividendScatterChart({ data, t }) {
  const [logScale, setLogScale] = useState(false)
  if (!data || data.length === 0) return null

  // En escala log filtramos los puntos con years_held=0 (log(0) es indefinido)
  const chartData = logScale ? data.filter(d => Number(d.years_held) > 0) : data
  const maxTotal = Math.max(...chartData.map(d => d.total_eur), 1)

  const CustomDot = (props) => {
    const { cx, cy, payload } = props
    if (typeof cx !== 'number' || typeof cy !== 'number') return null
    const r = Math.max(6, Math.sqrt(payload.total_eur / maxTotal) * 20)
    return (
      <g>
        <circle cx={cx} cy={cy} r={r} fill="#10b981" fillOpacity={0.8} stroke="#fff" strokeWidth={1} />
        <text x={cx} y={cy - r - 4} textAnchor="middle" fontSize={10}
          fill="var(--text-muted)" style={{ pointerEvents: 'none' }}>
          {payload.yahoo_ticker}
        </text>
      </g>
    )
  }

  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload?.length) return null
    const d = payload[0].payload
    return (
      <div style={{ background: '#1e1b2e', border: '1px solid #10b981', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#e2e8f0' }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.name}</div>
        <div>Años en cartera: {Number(d.years_held).toFixed(1)}</div>
        <div style={{ color: '#10b981' }}>Yield anualizado: {Number(d.yield_on_cost).toFixed(2)} %</div>
        <div>Total dividendos: {Number(d.total_eur).toFixed(2)} €</div>
        <div style={{ color: 'var(--text-muted)' }}>{d.count} cobros</div>
      </div>
    )
  }

  const Toggle = () => (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.85rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
      <span>Eje X lineal</span>
      <div
        onClick={() => setLogScale(s => !s)}
        style={{
          width: 40, height: 20, borderRadius: 10, cursor: 'pointer',
          background: logScale ? '#6366f1' : 'var(--border)',
          position: 'relative', transition: 'background 0.2s', flexShrink: 0,
        }}
      >
        <div style={{
          position: 'absolute', top: 2, left: logScale ? 22 : 2,
          width: 16, height: 16, borderRadius: '50%',
          background: '#fff', transition: 'left 0.2s',
        }} />
      </div>
      <span>logarítmico</span>
    </label>
  )

  return (
    <div className="card" style={{ flex: '1 1 320px', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: '1rem' }}>{t('portfolio.div_scatter_title')}</h3>
        <Toggle />
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{ top: 24, right: 24, bottom: 20, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis
            type="number" dataKey="years_held"
            scale={logScale ? 'log' : 'auto'}
            domain={logScale ? [0.1, 'auto'] : ['auto', 'auto']}
            allowDataOverflow={logScale}
            label={{ value: t('portfolio.div_scatter_years'), position: 'insideBottom', offset: -8, fill: 'var(--text-muted)', fontSize: 12 }}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
            tickFormatter={v => `${Number(v).toFixed(1)}a`}
          />
          <YAxis
            type="number" dataKey="yield_on_cost"
            tickFormatter={v => `${v}%`}
            label={{ value: t('portfolio.div_scatter_yield'), angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 12 }}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
          />
          <ZAxis type="number" dataKey="total_eur" range={[30, 600]} />
          <ReTooltip content={<CustomTooltip />} />
          <Scatter data={chartData} shape={<CustomDot />} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
