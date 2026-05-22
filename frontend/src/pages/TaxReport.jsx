import { useEffect, useState } from 'react'
import { api } from '../api/client'
import './TaxReport.css'

const CURRENT_YEAR = new Date().getFullYear()

// Tramos base del ahorro IRPF (vigentes desde 2023)
const BRACKETS = [
  { limit: 6_000,   rate: 19 },
  { limit: 50_000,  rate: 21 },
  { limit: 200_000, rate: 23 },
  { limit: 300_000, rate: 27 },
  { limit: Infinity, rate: 28 },
]

function computeTax(base) {
  if (base <= 0) return 0
  let remaining = base
  let tax = 0
  let prev = 0
  for (const { limit, rate } of BRACKETS) {
    const slice = Math.min(remaining, limit - prev)
    tax += slice * rate / 100
    remaining -= slice
    prev = limit
    if (remaining <= 0) break
  }
  return tax
}

function marginalRate(base) {
  if (base <= 0) return BRACKETS[0].rate
  let prev = 0
  for (const { limit, rate } of BRACKETS) {
    if (base <= limit) return rate
    prev = limit
  }
  return BRACKETS[BRACKETS.length - 1].rate
}

function eur(val) {
  return new Intl.NumberFormat('es-ES', {
    style: 'currency', currency: 'EUR', minimumFractionDigits: 2,
  }).format(val)
}

function SummaryCard({ label, value, sub, positive }) {
  const cls = value === 0 ? '' : value > 0 ? (positive ? 'pos' : 'neg') : (positive ? 'neg' : 'pos')
  return (
    <div className="tax-card">
      <div className="tax-card-label">{label}</div>
      <div className={`tax-card-value ${cls}`}>{eur(value)}</div>
      {sub && <div className="tax-card-sub">{sub}</div>}
    </div>
  )
}

function BracketBar({ base }) {
  if (base <= 0) return null

  // Construir segmentos coloreados
  const segments = []
  let remaining = base
  let prev = 0
  for (const { limit, rate } of BRACKETS) {
    const slice = Math.min(remaining, limit - prev)
    if (slice > 0) segments.push({ rate, amount: slice, pct: slice / base * 100 })
    remaining -= slice
    prev = limit
    if (remaining <= 0) break
  }

  const colors = { 19: '#4CAF50', 21: '#8BC34A', 23: '#FFC107', 27: '#FF9800', 28: '#F44336' }

  return (
    <div className="bracket-wrap">
      <div className="bracket-title">Distribución por tramos</div>
      <div className="bracket-bar">
        {segments.map((s, i) => (
          <div
            key={i}
            className="bracket-segment"
            style={{ width: `${s.pct}%`, background: colors[s.rate] }}
            title={`${s.rate}%: ${eur(s.amount)}`}
          />
        ))}
      </div>
      <div className="bracket-legend">
        {segments.map((s, i) => (
          <span key={i} className="bracket-legend-item">
            <span className="bracket-dot" style={{ background: colors[s.rate] }} />
            {s.rate}% — {eur(s.amount)}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function TaxReport() {
  const [summary, setSummary]   = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [taxYear, setTaxYear]   = useState(CURRENT_YEAR - 1)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.get(`/reports/tax/${CURRENT_YEAR}/summary`)
      .then(setSummary)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  function openReport() {
    window.open(`/api/reports/tax/${taxYear}/html`, '_blank')
  }

  const base = summary
    ? Math.max(0, summary.net_capital_result_eur) + summary.total_dividends_net_eur
    : 0

  return (
    <div>
      {/* ── Año en curso ── */}
      <div style={{ marginBottom: 24 }}>
        <h1>Ejercicio {CURRENT_YEAR} <span className="year-badge">en curso</span></h1>
        <p className="section-hint">
          Acumulado hasta hoy. Base imponible del ahorro estimada
          (plusvalías netas + dividendos netos).
        </p>
      </div>

      {loading && <div className="state-loading"><div className="spinner" /></div>}
      {error   && <div className="state-error" style={{ padding: 8 }}>{error}</div>}

      {summary && (
        <>
          <div className="tax-cards">
            <SummaryCard
              label="Resultado neto ventas"
              value={summary.net_capital_result_eur}
              sub={
                summary.total_losses_disallowed_eur < 0
                  ? `Pérd. no computables: ${eur(summary.total_losses_disallowed_eur)}`
                  : null
              }
              positive
            />
            <SummaryCard
              label="Dividendos netos"
              value={summary.total_dividends_net_eur}
              sub={`Bruto ${eur(summary.total_dividends_gross_eur)} · Ret. ${eur(summary.total_dividends_withholding_eur)}`}
              positive
            />
            <SummaryCard
              label="Comisiones pagadas"
              value={summary.total_commission_eur}
              sub="Ya descontadas del coste de adquisición"
              positive={false}
            />
            <div className="tax-card tax-card-accent">
              <div className="tax-card-label">Base imponible estimada</div>
              <div className="tax-card-value pos">{eur(base)}</div>
              <div className="tax-card-sub">
                Tramo marginal: <strong>{marginalRate(base)}%</strong>
                &nbsp;·&nbsp;Cuota estimada: <strong>{eur(computeTax(base))}</strong>
              </div>
            </div>
          </div>

          <BracketBar base={base} />

          {summary.warnings.length > 0 && (
            <div className="tax-warnings">
              {summary.warnings.map((w, i) => (
                <p key={i} className="tax-warning-item">{w}</p>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Informe completo de ejercicios pasados ── */}
      <div className="card" style={{ marginTop: 32 }}>
        <h2>Informe completo por ejercicio</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: '0.9rem' }}>
          Abre el informe detallado del año seleccionado en una pestaña nueva.
          Usa <strong>Ctrl+P</strong> → &ldquo;Guardar como PDF&rdquo; para descargarlo.
        </p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            value={taxYear}
            onChange={e => setTaxYear(Number(e.target.value))}
            style={{ width: 'auto' }}
          >
            {Array.from({ length: 10 }, (_, i) => CURRENT_YEAR - 1 - i).map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <button className="btn-primary btn-sm" onClick={openReport}>
            Ver informe fiscal
          </button>
        </div>
      </div>
    </div>
  )
}
