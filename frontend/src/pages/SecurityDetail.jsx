import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { api } from '../api/client'

function fmt(val, dec = 2) {
  if (val == null) return '—'
  return Number(val).toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec })
}
function fmtShares(val) {
  if (val == null) return '—'
  const n = Number(val)
  return n % 1 === 0
    ? n.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
    : n.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 6 })
}
function sign(val) { return Number(val) >= 0 ? '+' : '' }
function cls(val)  { return Number(val) > 0 ? 'pos' : Number(val) < 0 ? 'neg' : 'neu' }

function totalOp(tx) {
  const base = Number(tx.shares) * Number(tx.price)
  return tx.type === 'buy' ? base + Number(tx.fee) : base - Number(tx.fee)
}

function TxRow({ tx, onDelete, onEdit }) {
  return (
    <tr>
      <td>{tx.date}</td>
      <td className="num">{fmtShares(tx.shares)}</td>
      <td className="num">{fmt(tx.price)}</td>
      <td className="num">{fmt(tx.fee)}</td>
      <td className="num">{tx.currency}</td>
      <td className="num">{fmt(totalOp(tx))}</td>
      <td style={{ display: 'flex', gap: 4 }}>
        <button className="btn-ghost btn-sm" onClick={() => onEdit(tx)}>✎</button>
        <button className="btn-danger btn-sm" onClick={() => onDelete(tx.id)}>✕</button>
      </td>
    </tr>
  )
}

function DivRow({ div, onDelete, onEdit }) {
  return (
    <tr>
      <td>{div.date}</td>
      <td className="num">{fmt(div.shares_at_date, 4)}</td>
      <td className="num">{fmt(div.gross_per_share)}</td>
      <td className="num">{fmt(div.gross_amount)}</td>
      <td className="num">{div.currency}</td>
      <td style={{ display: 'flex', gap: 4 }}>
        <button className="btn-ghost btn-sm" onClick={() => onEdit(div)}>✎</button>
        <button className="btn-danger btn-sm" onClick={() => onDelete(div.id)}>✕</button>
      </td>
    </tr>
  )
}

function AddTxModal({ positionId, onClose, onAdded, initialType = 'buy', editTx = null }) {
  const [form, setForm] = useState(editTx ? {
    type: editTx.type,
    date: editTx.date,
    shares: String(editTx.shares),
    price: String(editTx.price),
    fee: String(editTx.fee),
    currency: editTx.currency,
    exchange_rate: String(editTx.exchange_rate),
  } : {
    type: initialType, date: new Date().toISOString().slice(0, 10),
    shares: '', price: '', fee: '0', currency: 'EUR', exchange_rate: '1',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  function field(name) {
    return { value: form[name], onChange: e => setForm(f => ({ ...f, [name]: e.target.value })) }
  }

  async function submit(e) {
    e.preventDefault()
    const errs = []
    if (Number(form.shares) <= 0) errs.push('Las acciones deben ser > 0')
    if (Number(form.price) <= 0) errs.push('El precio debe ser > 0')
    if (Number(form.exchange_rate) <= 0) errs.push('El tipo de cambio debe ser > 0')
    if (errs.length) { setError(errs.join('. ')); return }
    setBusy(true); setError(null)
    try {
      const payload = {
        ...form,
        shares: Number(form.shares),
        price: Number(form.price),
        fee: Number(form.fee),
        exchange_rate: Number(form.exchange_rate),
      }
      if (editTx) {
        await api.patch(`/portfolio/${positionId}/transactions/${editTx.id}`, payload)
      } else {
        await api.post(`/portfolio/${positionId}/transactions`, payload)
      }
      onAdded()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>{editTx ? 'Editar transacción' : 'Nueva transacción'}</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Tipo</label>
              <select {...field('type')}>
                <option value="buy">Compra</option>
                <option value="sell">Venta</option>
              </select>
            </div>
            <div className="form-group" style={{ flex: 2 }}>
              <label>Fecha</label>
              <input type="date" {...field('date')} />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Acciones</label>
              <input type="number" step="any" min="0" {...field('shares')} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Precio</label>
              <input type="number" step="any" min="0" {...field('price')} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Comisión</label>
              <input type="number" step="any" min="0" {...field('fee')} />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Divisa</label>
              <select {...field('currency')}>
                <option value="EUR">EUR</option>
                <option value="USD">USD</option>
              </select>
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Tipo EUR/USD</label>
              <input type="number" step="any" {...field('exchange_rate')} />
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Guardando…' : 'Guardar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function AddDivModal({ positionId, onClose, onAdded, editDiv = null }) {
  const [form, setForm] = useState(editDiv ? {
    date: editDiv.date,
    shares_at_date: String(editDiv.shares_at_date),
    gross_per_share: String(editDiv.gross_per_share),
    gross_amount: String(editDiv.gross_amount),
    currency: editDiv.currency,
    exchange_rate: String(editDiv.exchange_rate),
  } : {
    date: new Date().toISOString().slice(0, 10),
    shares_at_date: '', gross_per_share: '', gross_amount: '',
    currency: 'EUR', exchange_rate: '1',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  function field(name) {
    return { value: form[name], onChange: e => setForm(f => ({ ...f, [name]: e.target.value })) }
  }

  async function submit(e) {
    e.preventDefault()
    const errs = []
    if (Number(form.shares_at_date) <= 0) errs.push('Las acciones deben ser > 0')
    if (Number(form.gross_per_share) <= 0) errs.push('El dividendo por acción debe ser > 0')
    if (Number(form.gross_amount) <= 0) errs.push('El total bruto debe ser > 0')
    if (Number(form.exchange_rate) <= 0) errs.push('El tipo de cambio debe ser > 0')
    if (errs.length) { setError(errs.join('. ')); return }
    setBusy(true); setError(null)
    try {
      const payload = {
        ...form,
        shares_at_date: Number(form.shares_at_date),
        gross_per_share: Number(form.gross_per_share),
        gross_amount: Number(form.gross_amount),
        withholding_tax: 0,
        exchange_rate: Number(form.exchange_rate),
      }
      if (editDiv) {
        await api.patch(`/portfolio/${positionId}/dividends/${editDiv.id}`, payload)
      } else {
        await api.post(`/portfolio/${positionId}/dividends`, payload)
      }
      onAdded()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>{editDiv ? 'Editar dividendo' : 'Nuevo dividendo'}</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Fecha</label>
              <input type="date" {...field('date')} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Acciones en posesión</label>
              <input type="number" step="any" min="0" {...field('shares_at_date')} required />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>€/acción (bruto)</label>
              <input type="number" step="any" min="0" {...field('gross_per_share')} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Total bruto</label>
              <input type="number" step="any" min="0" {...field('gross_amount')} required />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Divisa</label>
              <select {...field('currency')}>
                <option value="EUR">EUR</option>
                <option value="USD">USD</option>
              </select>
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Tipo EUR/USD</label>
              <input type="number" step="any" {...field('exchange_rate')} />
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Guardando…' : 'Guardar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

const MARKETS    = ['ibex35', 'continuo', 'nasdaq']
const CURRENCIES = ['EUR', 'USD']

function EditSecurityModal({ security, onClose, onSaved }) {
  const [form, setForm] = useState({
    name:          security.name,
    isin:          security.isin          ?? '',
    yahoo_ticker:  security.yahoo_ticker,
    google_ticker: security.google_ticker ?? '',
    market:        security.market,
    currency:      security.currency,
  })
  const [busy, setBusy]   = useState(false)
  const [error, setError] = useState(null)

  function field(name) {
    return { value: form[name], onChange: e => setForm(f => ({ ...f, [name]: e.target.value })) }
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const body = { ...form }
      if (!body.isin)          delete body.isin
      if (!body.google_ticker) delete body.google_ticker
      const updated = await api.patch(`/securities/${security.id}`, body)
      // Refresca los datos de precio con el nuevo ticker
      await api.post(`/markets/${security.id}/refresh`).catch(() => {})
      onSaved(updated)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>Editar valor</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="card-row">
            <div className="form-group" style={{ flex: 2 }}>
              <label>Nombre *</label>
              <input type="text" {...field('name')} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>ISIN</label>
              <input type="text" {...field('isin')} />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Yahoo Ticker *</label>
              <input type="text" {...field('yahoo_ticker')} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Google Ticker</label>
              <input type="text" {...field('google_ticker')} />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Mercado *</label>
              <select {...field('market')}>
                {MARKETS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Divisa *</label>
              <select {...field('currency')}>
                {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Guardando…' : 'Guardar y refrescar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function SecurityDetail() {
  const { id } = useParams()
  const secId = parseInt(id, 10)

  const [security, setSecurity]     = useState(null)
  const [snapshot, setSnapshot]     = useState(null)
  const [history, setHistory]       = useState([])
  const [transactions, setTxs]      = useState([])
  const [dividends, setDivs]        = useState([])
  const [positionId, setPositionId]   = useState(null)
  const [posResult, setPosResult]     = useState(null)
  const [isClosed, setIsClosed]       = useState(false)
  const [closedSummary, setClosedSummary] = useState(null)
  const [showTxModal, setTxModal]     = useState(false)
  const [txModalType, setTxModalType] = useState('buy')
  const [editingTx, setEditingTx]     = useState(null)
  const [showDivModal, setDivModal]   = useState(false)
  const [editingDiv, setEditingDiv]   = useState(null)
  const [editingNotes, setEditingNotes] = useState(false)
  const [notesVal, setNotesVal]         = useState('')
  const [startingTracking, setStarting] = useState(false)
  const [error, setError]           = useState(null)
  const [opError, setOpError]       = useState(null)
  const [isFav, setIsFav]           = useState(false)
  const [showEditSec, setShowEditSec] = useState(false)

  async function loadAll() {
    setPosResult(null)
    setIsClosed(false)
    setClosedSummary(null)
    try {
      const [sec, snap, hist, posResult, favs] = await Promise.all([
        api.get(`/securities/${secId}`),
        api.get(`/markets/${secId}/snapshot`).catch(() => null),
        api.get(`/markets/${secId}/history`).catch(() => []),
        api.get(`/portfolio/by-security/${secId}`).catch(() => null),
        api.get('/favorites'),
      ])
      setSecurity(sec)
      setSnapshot(snap)
      setHistory(hist.slice(-365))
      setIsFav(favs.some(f => f.security_id === secId))

      if (posResult) {
        // Posición abierta encontrada directamente
        setPositionId(posResult.position_id)
        setPosResult(posResult)
        setIsClosed(false)
        setNotesVal(posResult.notes ?? '')
        const [txs, divs] = await Promise.all([
          api.get(`/portfolio/${posResult.position_id}/transactions`),
          api.get(`/portfolio/${posResult.position_id}/dividends`),
        ])
        setTxs(txs)
        setDivs(divs)
      } else {
        // Buscar en posiciones cerradas
        const closedAll = await api.get('/portfolio/closed').catch(() => [])
        const closedPos = closedAll.find(p => p.security_id === secId)
        if (closedPos) {
          setPositionId(closedPos.position_id)
          setIsClosed(true)
          setClosedSummary(closedPos)
          const [txs, divs] = await Promise.all([
            api.get(`/portfolio/${closedPos.position_id}/transactions`),
            api.get(`/portfolio/${closedPos.position_id}/dividends`),
          ])
          setTxs(txs)
          setDivs(divs)
        }
      }
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { loadAll() }, [secId])

  async function deleteTx(txId) {
    if (!confirm('¿Eliminar esta transacción?')) return
    setOpError(null)
    try {
      await api.delete(`/portfolio/${positionId}/transactions/${txId}`)
      setTxs(ts => ts.filter(t => t.id !== txId))
    } catch (err) { setOpError(err.message) }
  }

  async function deleteDiv(divId) {
    if (!confirm('¿Eliminar este dividendo?')) return
    setOpError(null)
    try {
      await api.delete(`/portfolio/${positionId}/dividends/${divId}`)
      setDivs(ds => ds.filter(d => d.id !== divId))
    } catch (err) { setOpError(err.message) }
  }

  async function saveNotes() {
    setEditingNotes(false)
    try {
      await api.patch(`/portfolio/${positionId}/notes`, { notes: notesVal || null })
    } catch { /* silencioso */ }
  }

  async function toggleFav() {
    if (isFav) { await api.delete(`/favorites/${secId}`); setIsFav(false) }
    else        { await api.post(`/favorites/${secId}`);  setIsFav(true) }
  }

  async function refresh() {
    await api.post(`/markets/${secId}/refresh`).catch(() => {})
    loadAll()
  }

  if (error)     return <div className="state-error">{error}</div>
  if (!security) return <div className="state-loading"><div className="spinner" /></div>

  const pct    = snapshot?.daily_change_pct != null ? Number(snapshot.daily_change_pct) : null
  const pctCls = pct == null ? 'neu' : pct > 0 ? 'pos' : pct < 0 ? 'neg' : 'neu'
  const chartData = history.map(h => ({ date: h.date, close: Number(h.close) }))

  const buys  = transactions.filter(t => t.type === 'buy')
  const sells = transactions.filter(t => t.type === 'sell')
  const totalDivsGross = dividends.reduce(
    (s, d) => s + Number(d.gross_amount), 0
  )
  // Comisiones en EUR: fee / exchange_rate (igual que el resto de conversiones)
  const totalFeesEur = transactions.reduce(
    (s, tx) => s + Number(tx.fee) / Number(tx.exchange_rate), 0
  )
  // Ganancia en venta SIN comisiones: se añaden de nuevo las comisiones
  // ya descontadas en el cálculo FIFO, para mostrar el movimiento de precio puro.
  const grossSaleGainEur = isClosed && closedSummary
    ? Number(closedSummary.realized_pnl_eur) + totalFeesEur
    : 0

  return (
    <div>
      {opError && (
        <div
          className="state-error"
          style={{ marginBottom: 16, cursor: 'pointer', display: 'flex', justifyContent: 'space-between' }}
          onClick={() => setOpError(null)}
        >
          <span>{opError}</span>
          <span>✕</span>
        </div>
      )}
      {/* Cabecera */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>
            <span className="ticker">{security.yahoo_ticker}</span>{' '}
            <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>{security.name}</span>
          </h1>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span className="badge badge-market">{security.market}</span>
            <span className="badge" style={{ background: 'var(--bg-input)', color: 'var(--text-muted)' }}>{security.currency}</span>
            {security.isin && (
              <span style={{ fontFamily: 'var(--mono)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                ISIN: {security.isin}
              </span>
            )}
            {security.google_ticker && (
              <span style={{ fontFamily: 'var(--mono)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Google: {security.google_ticker}
              </span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-ghost btn-sm" onClick={toggleFav}>
            {isFav ? '★ Favorito' : '☆ Añadir a favoritos'}
          </button>
          <button className="btn-ghost btn-sm" onClick={() => setShowEditSec(true)}>✎ Editar</button>
          <button className="btn-ghost btn-sm" onClick={refresh}>↺ Actualizar</button>
        </div>
      </div>

      {/* Snapshot */}
      {snapshot && (
        <div className="card-row">
          <div className="card small">
            <div className="value">{fmt(snapshot.last_price)} {security.currency}</div>
            <div className="label">Precio actual</div>
          </div>
          <div className="card small">
            <div className={`value ${pctCls}`}>
              {pct != null ? `${pct >= 0 ? '+' : ''}${fmt(pct)}%` : '—'}
            </div>
            <div className="label">Var. día</div>
          </div>
          <div className="card small">
            <div className="value">{fmt(snapshot.min_1y)}</div>
            <div className="label">Mín. 1 año</div>
          </div>
          <div className="card small">
            <div className="value">{fmt(snapshot.max_1y)}</div>
            <div className="label">Máx. 1 año</div>
          </div>
        </div>
      )}

      {/* Resumen posición */}
      {(posResult || isClosed) && (
        <div className="card-row">
          <div className="card small">
            <div className="value">{posResult ? fmtShares(posResult.shares) : '0'}</div>
            <div className="label">Acciones en posesión</div>
          </div>
          <div className="card small">
            <div className="value">{fmt(posResult ? posResult.market_value_eur : 0)} €</div>
            <div className="label">Valor actual</div>
          </div>
          {isClosed && closedSummary && (
            <>
              <div className="card small">
                <div className={`value ${cls(grossSaleGainEur)}`}>
                  {sign(grossSaleGainEur)}{fmt(grossSaleGainEur)} €
                </div>
                <div className="label">Ganancia en venta</div>
              </div>
              <div className="card small">
                <div className="value">{fmt(closedSummary.dividends_eur)} €</div>
                <div className="label">Dividendos (bruto)</div>
              </div>
              <div className="card small">
                <div className="value neg">{totalFeesEur > 0 ? `-${fmt(totalFeesEur)}` : fmt(totalFeesEur)} €</div>
                <div className="label">Comisiones pagadas</div>
              </div>
              <div className="card small">
                <div className={`value ${cls(closedSummary.total_profit_eur)}`}>
                  {sign(closedSummary.total_profit_eur)}{fmt(closedSummary.total_profit_eur)} €
                </div>
                <div className="label">B/P Total</div>
              </div>
            </>
          )}
          {posResult && (
            <>
              <div className="card small">
                <div className="value">{fmt(posResult.cost_eur)} €</div>
                <div className="label">Invertido</div>
              </div>
              <div className="card small">
                <div className={`value ${cls(posResult.unrealized_pnl_eur)}`}>
                  {sign(posResult.unrealized_pnl_eur)}{fmt(posResult.unrealized_pnl_eur)} €
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                  {sign(posResult.unrealized_pnl_pct)}{fmt(posResult.unrealized_pnl_pct)}%
                </div>
                <div className="label">B/P latente</div>
              </div>
              <div className="card small">
                <div className="value">{fmt(posResult.dividends_eur)} €</div>
                <div className="label">Dividendos (bruto)</div>
              </div>
              <div className="card small">
                <div className="value neg">{totalFeesEur > 0 ? `-${fmt(totalFeesEur)}` : fmt(totalFeesEur)} €</div>
                <div className="label">Comisiones pagadas</div>
              </div>
              <div className="card small">
                <div className={`value ${cls(posResult.total_profit_eur)}`}>
                  {sign(posResult.total_profit_eur)}{fmt(posResult.total_profit_eur)} €
                </div>
                <div className="label">B/P Total</div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Notas de posición */}
      {positionId && (
        <div className="card" style={{ padding: '10px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', minWidth: 48, paddingTop: 2 }}>Notas</span>
            {editingNotes ? (
              <textarea
                autoFocus
                value={notesVal}
                onChange={e => setNotesVal(e.target.value)}
                onBlur={saveNotes}
                onKeyDown={e => { if (e.key === 'Escape') { setEditingNotes(false); setNotesVal(posResult?.notes ?? '') } }}
                style={{ flex: 1, resize: 'vertical', minHeight: 48, fontFamily: 'inherit', fontSize: '0.85rem', padding: '4px 6px', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }}
              />
            ) : (
              <span
                style={{ flex: 1, fontSize: '0.85rem', color: notesVal ? 'var(--text)' : 'var(--text-muted)', cursor: 'pointer', padding: '2px 0' }}
                title="Clic para editar"
                onClick={() => setEditingNotes(true)}
              >
                {notesVal || '— añadir nota'}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Gráfico */}
      {chartData.length > 0 && (
        <div className="card">
          <h2>Histórico (último año)</h2>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="date"
                  tickFormatter={d => d.slice(5)}
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} width={55} domain={['auto', 'auto']} />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6 }}
                  labelStyle={{ color: 'var(--text-muted)' }}
                  itemStyle={{ color: 'var(--accent)' }}
                  formatter={v => [fmt(v), 'Precio']}
                />
                <Line type="monotone" dataKey="close" stroke="var(--accent)" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Compras */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h2 style={{ marginBottom: 0 }}>Compras</h2>
          {positionId
            ? <button className="btn-primary btn-sm" onClick={() => { setTxModalType('buy'); setEditingTx(null); setTxModal(true) }}>+ Añadir</button>
            : (
              <button
                className="btn-ghost btn-sm"
                disabled={startingTracking}
                onClick={async () => {
                  setStarting(true)
                  try {
                    const pos = await api.post('/portfolio/positions', { security_id: secId })
                    setPositionId(pos.id)
                    setTxModalType('buy')
                    setEditingTx(null)
                    setTxModal(true)
                  } catch (err) { setError(err.message) }
                  finally { setStarting(false) }
                }}
              >
                {startingTracking ? 'Creando…' : '+ Empezar a seguir'}
              </button>
            )
          }
        </div>
        {buys.length === 0 ? (
          <div className="state-empty" style={{ padding: 20 }}>
            {positionId ? 'Sin compras registradas' : 'Haz clic en "Empezar a seguir" para registrar operaciones'}
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th className="num">Acciones</th>
                  <th className="num">Precio</th>
                  <th className="num">Comisión</th>
                  <th className="num">Divisa</th>
                  <th className="num">Total op.</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>{buys.map(tx => <TxRow key={tx.id} tx={tx} onDelete={deleteTx} onEdit={tx => { setEditingTx(tx); setTxModal(true) }} />)}</tbody>
            </table>
          </div>
        )}
      </div>

      {/* Ventas */}
      {(sells.length > 0 || positionId) && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ marginBottom: 0 }}>Ventas</h2>
            {positionId && (
              <button
                className="btn-primary btn-sm"
                onClick={() => { setTxModalType('sell'); setEditingTx(null); setTxModal(true) }}
              >
                + Añadir
              </button>
            )}
          </div>
          {sells.length === 0 ? (
            <div className="state-empty" style={{ padding: 20 }}>Sin ventas registradas</div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th className="num">Acciones</th>
                    <th className="num">Precio</th>
                    <th className="num">Comisión</th>
                    <th className="num">Divisa</th>
                    <th className="num">Total op.</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>{sells.map(tx => <TxRow key={tx.id} tx={tx} onDelete={deleteTx} onEdit={tx => { setEditingTx(tx); setTxModal(true) }} />)}</tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Dividendos */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h2 style={{ marginBottom: 0 }}>
            Dividendos
            {totalDivsGross > 0 && (
              <span style={{ marginLeft: 10, fontSize: '0.85rem', color: 'var(--green)', fontFamily: 'var(--mono)' }}>
                +{fmt(totalDivsGross)} €
              </span>
            )}
          </h2>
          {positionId && (
            <button className="btn-ghost btn-sm" onClick={() => { setEditingDiv(null); setDivModal(true) }}>+ Añadir</button>
          )}
        </div>
        {dividends.length === 0 ? (
          <div className="state-empty" style={{ padding: 20 }}>Sin dividendos registrados</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th className="num">Acciones</th>
                  <th className="num">€/acc.</th>
                  <th className="num">Bruto</th>
                  <th className="num">Divisa</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>{dividends.map(d => <DivRow key={d.id} div={d} onDelete={deleteDiv} onEdit={d => { setEditingDiv(d); setDivModal(true) }} />)}</tbody>
            </table>
          </div>
        )}
      </div>

      {showEditSec && (
        <EditSecurityModal
          security={security}
          onClose={() => setShowEditSec(false)}
          onSaved={updated => { setSecurity(updated); setShowEditSec(false); loadAll() }}
        />
      )}
      {showTxModal && (
        <AddTxModal
          positionId={positionId}
          initialType={txModalType}
          editTx={editingTx}
          onClose={() => { setTxModal(false); setEditingTx(null) }}
          onAdded={() => { setTxModal(false); setEditingTx(null); loadAll() }}
        />
      )}
      {showDivModal && (
        <AddDivModal
          positionId={positionId}
          editDiv={editingDiv}
          onClose={() => { setDivModal(false); setEditingDiv(null) }}
          onAdded={() => { setDivModal(false); setEditingDiv(null); loadAll() }}
        />
      )}
    </div>
  )
}
