import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'
import PortfolioChartsPanel, {
  DistributionChart,
  GroupedDistributionChart,
  HistoryChart,
  PnLChart,
  ClosedScatterChart,
  DividendBarChart,
  DividendScatterChart,
} from '../components/PortfolioChartsPanel'
import AssetTypeFilter, { matchesTypes, presentTypes } from '../components/AssetTypeFilter'
import { useSortableData, SortableHead } from '../hooks/useSortableData'

// Persistencia de la selección de tipos por pantalla.
function loadSegTypes(key) {
  try { return JSON.parse(localStorage.getItem(key)) || [] } catch { return [] }
}

function assetTypeKey(marketCode, isFund, marketType) {
  if (marketType) return marketType
  if (isFund) return 'fund'
  const c = (marketCode ?? '').toLowerCase()
  if (c.includes('etf'))    return 'etf'
  if (c.includes('crypto')) return 'crypto'
  return 'stock'
}

function AssetBadge({ marketCode, isFund, marketType, t }) {
  const type = assetTypeKey(marketCode, isFund, marketType)
  return <span className={`badge-asset ${type}`}>{t(`badge.${type}`)}</span>
}

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

/** Convierte meses a "X año(s) y Y mes(es)" para la tabla de dividendos. */
function fmtYearsMonths(months) {
  const years = Math.floor(months / 12)
  const rem   = months % 12
  if (years === 0) return `${rem} ${rem === 1 ? 'mes' : 'meses'}`
  if (rem   === 0) return `${years} ${years === 1 ? 'año' : 'años'}`
  return `${years} ${years === 1 ? 'año' : 'años'} y ${rem} ${rem === 1 ? 'mes' : 'meses'}`
}

/** Estilo de scroll vertical para tablas largas (>10 filas). */
function tableScrollStyle(count) {
  return count > 10 ? { maxHeight: 540, overflowY: 'auto' } : {}
}

function sign(val) { return Number(val) >= 0 ? '+' : '' }
function cls(val)  { return Number(val) > 0 ? 'pos' : Number(val) < 0 ? 'neg' : 'neu' }

function Card({ label, value, sub, clsName }) {
  return (
    <div className="card small">
      <div className={`value ${clsName ?? ''}`}>{value}</div>
      {sub && <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{sub}</div>}
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
  const [segTypes, setSegTypes]           = useState(() => loadSegTypes('portfolioSegTypes'))
  const [xirr, setXirr]                   = useState(null)
  const [periods, setPeriods]             = useState(null)
  const [searchOpen, setSearchOpen]       = useState('')
  const [searchClosed, setSearchClosed]   = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      api.get('/portfolio'),
      api.get('/portfolio/closed'),
      api.get('/portfolio/closed-analytics').catch(() => []),
      api.get('/portfolio/dividends-by-security').catch(() => []),
    ])
      .then(([open, cls, analytics, divsBySec]) => {
        setPositions(open)
        setClosed(cls)
        setClosedAn(analytics || [])
        setDivsBySec(divsBySec || [])
        // Sanear selección persistida: descartar tipos que ya no existen en la
        // cartera (evita una vista vacía sin chip resaltado al haber vendido todo
        // de un tipo previamente seleccionado).
        const avail = presentTypes([...(open || []), ...(cls || [])])
        const clean = segTypes.filter(tp => avail.includes(tp))
        if (clean.length !== segTypes.length) changeSeg(clean)
      })
      .catch(err => setError(err.message))
  }, [])

  // El histórico y la TIR se agregan en el backend; se re-piden al segmentar.
  useEffect(() => {
    const qs = segTypes.length ? `?types=${segTypes.join(',')}` : ''
    api.get(`/portfolio/history${qs}`).then(setHistory).catch(() => setHistory([]))
    api.get(`/portfolio/xirr${qs}`).then(setXirr).catch(() => setXirr(null))
    api.get(`/portfolio/period-returns${qs}`).then(setPeriods).catch(() => setPeriods(null))
  }, [segTypes])

  function changeSeg(next) {
    setSegTypes(next)
    localStorage.setItem('portfolioSegTypes', JSON.stringify(next))
  }

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

  // IMPORTANTE: ningún hook (useSortableData) puede ir después de un return
  // condicional. Por eso los datasets y los hooks de ordenación se calculan
  // ANTES de los guards de error/carga, usando arrays seguros (positions puede
  // ser null en el primer render). Mover los guards arriba rompería las reglas
  // de hooks ("rendered more hooks than during the previous render" → pantalla
  // en negro al cargar los datos).
  const safePositions = positions || []

  // Tipos presentes (abiertas + cerradas) y datasets filtrados por la segmentación.
  const available  = presentTypes([...safePositions, ...closed])
  const fPositions = safePositions.filter(p => matchesTypes(p, segTypes))
  const fClosed    = closed.filter(p => matchesTypes(p, segTypes))
  const fClosedAn  = closedAnalytics.filter(p => matchesTypes(p, segTypes))
  const fDivsBySec = dividendsBySec.filter(d => matchesTypes(d, segTypes))

  // Buscador (por ticker o nombre) sobre cartera abierta y cerrada.
  const matchSearch = (p, q) => {
    if (!q.trim()) return true
    const s = q.trim().toLowerCase()
    return (p.yahoo_ticker || '').toLowerCase().includes(s)
      || (p.name || '').toLowerCase().includes(s)
  }
  const searchedOpen   = fPositions.filter(p => matchSearch(p, searchOpen))
  const searchedClosed = fClosed.filter(p => matchSearch(p, searchClosed))

  // Ordenación por cabecera (cliente, no persistente).
  const openSort   = useSortableData(searchedOpen)
  const closedSort = useSortableData(searchedClosed)

  // Guards DESPUÉS de todos los hooks.
  if (error)      return <div className="state-error">{error}</div>
  if (!positions) return <div className="state-loading"><div className="spinner" /></div>

  const numN = v => (v != null ? Number(v) : null)
  const openColumns = [
    { key: 'security', label: t('portfolio.col_security'), accessor: p => p.name },
    { key: 'shares',   label: t('portfolio.col_shares'),     className: 'num', accessor: p => numN(p.shares) },
    { key: 'avg',      label: t('portfolio.col_avg'),        className: 'num', accessor: p => numN(p.avg_cost_eur) },
    { key: 'cost',     label: t('portfolio.col_cost'),       className: 'num', accessor: p => numN(p.cost_eur) },
    { key: 'price',    label: t('portfolio.col_price'),      className: 'num', accessor: p => numN(p.current_price) },
    { key: 'value',    label: t('portfolio.col_value'),      className: 'num', accessor: p => numN(p.market_value_eur) },
    { key: 'unreal',   label: t('portfolio.col_unrealized'), className: 'num', accessor: p => numN(p.unrealized_pnl_eur) },
    { key: 'pct',      label: t('portfolio.col_pct'),        className: 'num', accessor: p => numN(p.unrealized_pnl_pct) },
    { key: 'dayeur',   label: `${t('portfolio.col_daily')} €`, className: 'num', accessor: p => numN(p.daily_change_eur) },
    { key: 'daypct',   label: `${t('portfolio.col_daily')} %`, className: 'num', accessor: p => numN(p.daily_change_pct) },
    { key: 'divs',     label: t('portfolio.col_divs'),       className: 'num', accessor: p => numN(p.dividends_eur) },
    { key: 'total',    label: t('portfolio.col_total'),      className: 'num', accessor: p => numN(p.total_profit_eur) },
    { key: 'range',    label: t('portfolio.col_range'),      className: 'num', accessor: p => numN(p.max_1y) },
    { key: 'target',   label: t('portfolio.col_target'),     className: 'num', accessor: p => numN(p.target_sell_price) },
    { key: 'targetpct', label: t('portfolio.col_target_pct'), className: 'num',
      accessor: p => (p.target_sell_price != null && p.current_price != null)
        ? (Number(p.target_sell_price) - Number(p.current_price)) / Number(p.current_price) * 100 : null },
    { key: 'alert',    label: t('markets.col_alert'), style: { textAlign: 'center' } },
    { key: 'actions',  label: '' },
  ]
  const closedColumns = [
    { key: 'security', label: t('portfolio.col_security'), accessor: p => p.name },
    { key: 'shares',   label: t('portfolio.col_shares'),   className: 'num', accessor: p => numN(p.shares_sold) },
    { key: 'cost',     label: t('portfolio.col_cost'),     className: 'num', accessor: p => numN(p.cost_eur) },
    { key: 'value',    label: t('portfolio.col_value'),    className: 'num', accessor: p => numN(p.proceeds_eur) },
    { key: 'realized', label: t('portfolio.col_realized'), className: 'num', accessor: p => numN(p.realized_pnl_eur) },
    { key: 'divs',     label: t('portfolio.col_divs'),     className: 'num', accessor: p => numN(p.dividends_eur) },
    { key: 'total',    label: t('portfolio.col_total'),    className: 'num', accessor: p => numN(p.total_profit_eur) },
  ]

  const totalValue    = fPositions.reduce((s, p) => s + Number(p.market_value_eur), 0)
  const totalCost     = fPositions.reduce((s, p) => s + Number(p.cost_eur), 0)
  const totalPnL      = fPositions.reduce((s, p) => s + Number(p.unrealized_pnl_eur), 0)
  const totalDivs     = fPositions.reduce((s, p) => s + Number(p.dividends_eur), 0)
                      + fClosed.reduce((s, p) => s + Number(p.dividends_eur), 0)
  const totalDayEur   = fPositions.reduce((s, p) => s + (p.daily_change_eur != null ? Number(p.daily_change_eur) : 0), 0)
  const realizedNet   = fPositions.reduce((s, p) => s + Number(p.realized_pnl_eur), 0)
                      + fClosed.reduce((s, p) => s + Number(p.realized_pnl_eur), 0)
  const totalFees     = fPositions.reduce((s, p) => s + Number(p.fees_eur), 0)
                      + fClosed.reduce((s, p) => s + Number(p.fees_eur), 0)
  const grossRealized = realizedNet + totalFees
  const bpTotal       = totalPnL + realizedNet + totalDivs

  return (
    <div>
      <h1>{t('portfolio.title')}</h1>

      <AssetTypeFilter value={segTypes} available={available} onChange={changeSeg} />

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
        <Card
          label={t('portfolio.xirr')}
          value={xirr?.xirr_pct != null ? `${sign(xirr.xirr_pct)}${fmt(xirr.xirr_pct)}%` : '—'}
          sub={t('portfolio.xirr_sub')}
          clsName={xirr?.xirr_pct != null ? cls(xirr.xirr_pct) : ''}
        />
      </div>

      {/* Rentabilidad por periodo (Modified Dietz) */}
      {periods && (periods.ytd != null || periods.y1 != null || periods.y3 != null || periods.total != null) && (
        <div className="period-returns">
          {[['ytd', 'portfolio.pr_ytd'], ['y1', 'portfolio.pr_1y'], ['y3', 'portfolio.pr_3y'], ['total', 'portfolio.pr_total']].map(([k, key]) => (
            periods[k] != null && (
              <div key={k} className="period-chip">
                <span className="period-label">{t(key)}</span>
                <span className={`period-val ${cls(periods[k])}`}>{sign(periods[k])}{fmt(periods[k])}%</span>
              </div>
            )
          ))}
        </div>
      )}

      {/* 2. Evolución de cartera (ancho completo) */}
      {fPositions.length > 0 && (
        <HistoryChart history={history} t={t} />
      )}

      {/* 3. Tabla posiciones abiertas */}
      {fPositions.length === 0 ? (
        <div className="state-empty">{t('portfolio.open')}</div>
      ) : (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
            <h2 style={{ margin: 0 }}>{t('portfolio.open')}</h2>
            <input
              type="search"
              value={searchOpen}
              onChange={e => setSearchOpen(e.target.value)}
              placeholder={t('markets.search_placeholder')}
              style={{ flex: '0 1 240px', padding: '5px 10px', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)', fontSize: '0.85rem' }}
            />
          </div>
          <div className="table-wrap" style={tableScrollStyle(openSort.sorted.length)}>
            <table>
              <SortableHead columns={openColumns} sortKey={openSort.sortKey} sortDir={openSort.sortDir} requestSort={openSort.requestSort} />
              <tbody>
                {openSort.sorted.map(p => {
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
                          <AssetBadge marketCode={p.market_code} isFund={p.is_fund_market} marketType={p.market_type} t={t} />
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
      {fPositions.length > 0 && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16, alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 320px', minWidth: 0 }}>
            <DistributionChart positions={fPositions} t={t} navigate={navigate} />
          </div>
          <div style={{ flex: '2 1 400px', minWidth: 0 }}>
            <PnLChart positions={fPositions} t={t} navigate={navigate} />
          </div>
        </div>
      )}

      {/* 4b. Distribución por tipo de producto y por divisa (si hay variedad) */}
      {fPositions.length > 0 && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16, alignItems: 'flex-start' }}>
          <GroupedDistributionChart positions={fPositions} groupBy="market_type" title={t('portfolio.dist_by_type')} t={t} />
          <GroupedDistributionChart positions={fPositions} groupBy="currency" title={t('portfolio.dist_by_currency')} t={t} />
        </div>
      )}

      {/* 5. Tabla posiciones cerradas */}
      {fClosed.length > 0 && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
            <h2 style={{ margin: 0 }}>{t('portfolio.closed')}</h2>
            <input
              type="search"
              value={searchClosed}
              onChange={e => setSearchClosed(e.target.value)}
              placeholder={t('markets.search_placeholder')}
              style={{ flex: '0 1 240px', padding: '5px 10px', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)', fontSize: '0.85rem' }}
            />
          </div>
          <div className="table-wrap" style={tableScrollStyle(closedSort.sorted.length)}>
            <table>
              <SortableHead columns={closedColumns} sortKey={closedSort.sortKey} sortDir={closedSort.sortDir} requestSort={closedSort.requestSort} />
              <tbody>
                {closedSort.sorted.map(p => (
                  <tr key={p.position_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/securities/${p.security_id}`)}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div className="ticker">{p.yahoo_ticker}</div>
                        <AssetBadge marketCode={p.market_code} isFund={p.is_fund_market} marketType={p.market_type} t={t} />
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
      {fClosedAn.length > 0 && (
        <ClosedScatterChart data={fClosedAn} t={t} />
      )}

      {/* 7. Tabla dividendos por acción */}
      {fDivsBySec.length > 0 && (
        <div className="card" style={{ marginTop: 24 }}>
          <h2>{t('portfolio.div_by_security_title')}</h2>
          <div className="table-wrap" style={tableScrollStyle(fDivsBySec.length)}>
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
                {fDivsBySec.map(d => (
                  <tr key={d.security_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/securities/${d.security_id}`)}>
                    <td>
                      <div className="ticker">{d.yahoo_ticker}</div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{d.name}</div>
                    </td>
                    <td className="num">{d.count}</td>
                    <td className="num">{fmtYearsMonths(d.months_held)}</td>
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
      {fDivsBySec.length > 0 && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 16 }}>
          <DividendBarChart data={fDivsBySec} t={t} navigate={navigate} />
          <DividendScatterChart data={fDivsBySec} t={t} />
        </div>
      )}
    </div>
  )
}
