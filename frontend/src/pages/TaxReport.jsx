import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'
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

function BracketBar({ base, t }) {
  if (base <= 0) return null

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
      <div className="bracket-title">{t('tax.brackets_title')}</div>
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
  const { t, locale } = useAppConfig()
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
    window.open(`/api/reports/tax/${taxYear}/html?lang=${locale}`, '_blank')
  }

  const base = summary
    ? Math.max(0, summary.net_capital_result_eur) + summary.total_dividends_net_eur
    : 0

  return (
    <div>
      {/* ── Año en curso ── */}
      <div style={{ marginBottom: 24 }}>
        <h1>{t('tax.year_current')} {CURRENT_YEAR} <span className="year-badge">{t('tax.in_progress')}</span></h1>
        <p className="section-hint">{t('tax.current_year_hint')}</p>
      </div>

      {loading && <div className="state-loading"><div className="spinner" /></div>}
      {error   && <div className="state-error" style={{ padding: 8 }}>{error}</div>}

      {summary && (
        <>
          <div className="tax-cards">
            <SummaryCard
              label={t('tax.card_net_sales')}
              value={summary.net_capital_result_eur}
              sub={
                <span>
                  {t('tax.card_net_sales_sub')}
                  {summary.total_losses_disallowed_eur < 0 && (
                    <><br />{t('tax.disallowed_losses')} {eur(summary.total_losses_disallowed_eur)}</>
                  )}
                </span>
              }
              positive
            />
            <SummaryCard
              label={t('tax.card_dividends')}
              value={summary.total_dividends_net_eur}
              sub={`${t('tax.gross')} ${eur(summary.total_dividends_gross_eur)} · ${t('tax.withholding_short')} ${eur(summary.total_dividends_withholding_eur)}`}
              positive
            />
            <SummaryCard
              label={t('tax.card_commissions')}
              value={summary.total_commission_eur}
              sub={t('tax.commissions_sub')}
              positive={false}
            />
            <div className="tax-card tax-card-accent">
              <div className="tax-card-label">{t('tax.card_taxbase')}</div>
              <div className="tax-card-value pos">{eur(base)}</div>
              <div className="tax-card-sub">
                {t('tax.marginal_rate')} <strong>{marginalRate(base)}%</strong>
                &nbsp;·&nbsp;{t('tax.estimated_tax')} <strong>{eur(computeTax(base))}</strong>
              </div>
            </div>
          </div>

          <BracketBar base={base} t={t} />

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
        <h2>{t('tax.full_report_title')}</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: '0.9rem' }}>
          {t('tax.full_report_hint')}
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
            {t('tax.open_report')}
          </button>
        </div>
      </div>
    </div>
  )
}
