import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'
import PortfolioChartsPanel, {
  DistributionChart,
  HistoryChart,
  PnLChart,
  ClosedScatterChart,
  DividendBarChart,
  DividendScatterChart,
} from '../components/PortfolioChartsPanel'

function assetTypeKey(marketCode) {
  const c = (marketCode ?? '').toLowerCase()
  if (c.includes('etf'))    return 'etf'
  if (c.includes('crypto')) return 'crypto'
  return 'stock'
}

function AssetBadge({ marketCode, t }) {
  const type = assetTypeKey(marketCode)
  return <span className={`badge-asset ${type}`}>{t(`badge.${type}`)}</span>
}

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
    if (isNaN(num) || num <= 0) return
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
  const { t } = useAppConfig()
  const [positions, setPositions]         = useState(null)
  const [closed, setClosed]               = useState([])
  const [history, setHistory]             = useState([])
  const [closedAnalytics, setClosedAn]    = useState([])
  const [dividendsBySec, setDivsBySec]    = useState([])
  const [error, setError]                 = useState(null)
  const [deleting, setDeleting]           = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      api.get('/portfolio'),
      api.get('/portfolio/closed'),
      api.get('/portfolio/history'),
      api.get('/portfolio/closed-analytics').catch(() => []),
      api.get('/portfolio/dividends-by-security').catch(() => []),
    ])
      .then(([open, cls, hist, analytics, divsBySec]) => {
        setPositions(open)
        setClosed(cls)
        setHistory(hist)
        setClosedAn(analytics)
        setDivsBySec(divsBySec)
      })
      .catch(err => setError(err.message))
  }, [])

  function handleTargetUpdate(positionId, newPrice) {
    setPositions(prev =>
      prev.map(p => p.position_id === positionId ? { ...p, target_sell_price: newPrice } : p)
    )
  }

  async function handleDeletePosition(pos) {
    if (!window.confirm(t('portfolio.delete_confirm').replace('{name}', pos.name))) return
    setDeleting(pos.position_id)
    try {
      await api.delete(`/portfolio/positions/${pos.position_id}`)
      setPositions(prev => prev.filter(p => p.position_id !== pos.position_id))
    } catch (err) {
      alert(err.message)
    } finally {
      setDeleting(null)
    }
  }

  if (error)      return <div className="state-error">{error}</div>
  if (!positions) return <div className="state-loading"><div className="spinner" /></div>

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
  const grossRealized = realizedNet + totalFees
  const bpTotal       = totalPnL + realizedNet + totalDivs

  return (
    <div>
      <h1>{t('portfolio.title')}</h1>

      {/* 1. Tarjetas resumen */}
      <div className="card-row">
        <Card label={t('portfolio.invested')}  value={`${fmt(totalCost)} €`} />
        <Card label={t('portfolio.value')}     value={`${fmt(totalValue)} €`} />
        <Card label={t('portfolio.unrealized')} value={`${sign(totalPnL)}${fmt(totalPnL)} €`} clsName={cls(totalPnL)} />
        <Card label={t('portfolio.today')}     value={`${sign(totalDayEur)}${fmt(totalDayEur)} €`} clsName={cls(totalDayEur)} />
        <Card label={t('portfolio.realized')}  value={`${sign(grossRealized)}${fmt(grossRealized)} €`} clsName={cls(grossRealized)} />
        <Card label={t('portfolio.dividends')} value={`${fmt(totalDivs)} €`} />
        <Card label={t('portfolio.fees')}      value={`-${fmt(totalFees)} €`} clsName="neg" />
        <Card label={t('portfolio.total')}     value={`${sign(bpTotal)}${fmt(bpTotal)} €`} clsName={cls(bpTotal)} />
      </div>

      {/* 2. Evolución de cartera (ancho completo) */}
      {positions.length > 0 && (
        <HistoryChart history={history} t={t} />
      )}

      {/* 3. Tabla posiciones abiertas */}
      {positions.length === 0 ? (
        <div className="state-empty">{t('portfolio.open')}</div>
      ) : (
        <div className="card">
          <h2>{t('portfolio.open')}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('portfolio.col_security')}</th>
                  <th className="num">{t('portfolio.col_shares')}</th>
                  <th className="num">{t('portfolio.col_avg')}</th>
                  <th className="num">{t('portfolio.col_cost')}</th>
                  <th className="num">{t('portfolio.col_price')}</th>
                  <th className="num">{t('portfolio.col_value')}</th>
                  <th className="num">{t('portfolio.col_unrealized')}</th>
                  <th className="num">{t('portfolio.col_pct')}</th>
                  <th className="num">{t('portfolio.col_daily')} €</th>
                  <th className="num">{t('portfolio.col_daily')} %</th>
                  <th className="num">{t('portfolio.col_divs')}</th>
                  <th className="num">{t('portfolio.col_total')}</th>
                  <th className="num">{t('portfolio.col_range')}</th>
                  <th className="num">{t('portfolio.col_target')}</th>
                  <th className="num">{t('portfolio.col_target_pct')}</th>
                  <th style={{ textAlign: 'center' }}>{t('markets.col_alert')}</th>
                  <th></th>
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
                    <tr key={p.position_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/securities/${p.security_id}`)}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div className="ticker">{p.yahoo_ticker}</div>
                          <AssetBadge marketCode={p.market_code} t={t} />
                        </div>
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
                      <td className={`num ${cls(p.unrealized_pnl_eur)}`}>{sign(p.unrealized_pnl_eur)}{fmt(p.unrealized_pnl_eur)}</td>
                      <td className={`num ${cls(p.unrealized_pnl_pct)}`}>{sign(p.unrealized_pnl_pct)}{fmt(p.unrealized_pnl_pct)}%</td>
                      <td className={`num ${p.daily_change_eur != null ? cls(p.daily_change_eur) : 'neu'}`}>
                        {p.daily_change_eur != null ? `${sign(p.daily_change_eur)}${fmt(p.daily_change_eur)}` : '—'}
                      </td>
                      <td className={`num ${p.daily_change_pct != null ? cls(p.daily_change_pct) : 'neu'}`}>
                        {p.daily_change_pct != null ? `${sign(p.daily_change_pct)}${fmt(p.daily_change_pct)}%` : '—'}
                      </td>
                      <td className="num">{fmt(p.dividends_eur)}</td>
                      <td className={`num ${cls(p.total_profit_eur)}`}>{sign(p.total_profit_eur)}{fmt(p.total_profit_eur)}</td>
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
                      <td style={{ textAlign: 'center' }} onClick={e => e.stopPropagation()}>
                        {!p.has_sells && (
                          <button
                            className="btn-ghost btn-sm"
                            title={t('portfolio.delete_title')}
                            disabled={deleting === p.position_id}
                            onClick={() => handleDeletePosition(p)}
                            style={{ color: 'var(--red, #ef4444)', padding: '2px 6px', fontSize: '0.8rem' }}
                          >🗑</button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 4. Distribución + B/P por acción (posiciones abiertas, flex responsive) */}
      {positions.length > 0 && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16, alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 320px', minWidth: 0 }}>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 4 }}>
              {t('portfolio.open')}
            </div>
            <DistributionChart positions={positions} t={t} navigate={navigate} />
          </div>
          <div style={{ flex: '2 1 400px', minWidth: 0 }}>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 4 }}>
              {t('portfolio.open')}
            </div>
            <PnLChart positions={positions} t={t} navigate={navigate} />
          </div>
        </div>
      )}

      {/* 5. Tabla posiciones cerradas */}
      {closed.length > 0 && (
        <div className="card">
          <h2>{t('portfolio.closed')}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('portfolio.col_security')}</th>
                  <th className="num">{t('portfolio.col_shares')}</th>
                  <th className="num">{t('portfolio.col_cost')}</th>
                  <th className="num">{t('portfolio.col_value')}</th>
                  <th className="num">{t('portfolio.col_realized')}</th>
                  <th className="num">{t('portfolio.col_divs')}</th>
                  <th className="num">{t('portfolio.col_total')}</th>
                </tr>
              </thead>
              <tbody>
                {closed.map(p => (
                  <tr key={p.position_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/securities/${p.security_id}`)}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div className="ticker">{p.yahoo_ticker}</div>
                        <AssetBadge marketCode={p.market_code} t={t} />
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{p.name}</div>
                    </td>
                    <td className="num">{fmt(p.shares_sold, 4)}</td>
                    <td className="num">{fmt(p.cost_eur)}</td>
                    <td className="num">{fmt(p.proceeds_eur)}</td>
                    <td className={`num ${cls(p.realized_pnl_eur)}`}>{sign(p.realized_pnl_eur)}{fmt(p.realized_pnl_eur)}</td>
                    <td className="num">{fmt(p.dividends_eur)}</td>
                    <td className={`num ${cls(p.total_profit_eur)}`}>{sign(p.total_profit_eur)}{fmt(p.total_profit_eur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 6. Scatter plot posiciones cerradas */}
      {closedAnalytics.length > 0 && (
        <ClosedScatterChart data={closedAnalytics} t={t} />
      )}

      {/* 7. Tabla dividendos por acción */}
      {dividendsBySec.length > 0 && (
        <div className="card" style={{ marginTop: 24 }}>
          <h2>{t('portfolio.div_by_security_title')}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('portfolio.col_security')}</th>
                  <th className="num">{t('portfolio.div_count')}</th>
                  <th className="num">{t('portfolio.div_months')}</th>
                  <th className="num">{t('portfolio.div_avg_yield')}</th>
                  <th className="num">{t('portfolio.div_avg_per_share')}</th>
                  <th className="num">{t('portfolio.div_total')}</th>
                </tr>
              </thead>
              <tbody>
                {dividendsBySec.map(d => (
                  <tr key={d.security_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/securities/${d.security_id}`)}>
                    <td>
                      <div className="ticker">{d.yahoo_ticker}</div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{d.name}</div>
                    </td>
                    <td className="num">{d.count}</td>
                    <td className="num">{d.months_held}</td>
                    <td className="num pos">{fmt(d.avg_yield_pct, 2)} %</td>
                    <td className="num">{fmt(d.avg_per_share, 4)}</td>
                    <td className="num pos">{fmt(d.total_eur)} €</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 8. Gráficas dividendos: bar chart + scatter yield on cost */}
      {dividendsBySec.length > 0 && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 16 }}>
          <DividendBarChart data={dividendsBySec} t={t} />
          <DividendScatterChart data={dividendsBySec} t={t} />
        </div>
      )}
    </div>
  )
}
