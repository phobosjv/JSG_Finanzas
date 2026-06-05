import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'
import { useAuth } from '../context/AuthContext'
import { useSortableData, SortableHead } from '../hooks/useSortableData'

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

/** Scroll vertical para tablas con >10 filas. */
function tableScrollStyle(count) {
  return count > 10 ? { maxHeight: 540, overflowY: 'auto' } : {}
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

function AddTxModal({ positionId, onClose, onAdded, initialType = 'buy', editTx = null, isFund = false }) {
  const { t, currencies: CURRENCIES } = useAppConfig()
  const [form, setForm] = useState(editTx ? {
    type: editTx.type,
    date: editTx.date,
    shares: String(editTx.shares),
    price: String(editTx.price),
    // En fondos se trabaja por importe total = participaciones × precio.
    amount: String(Number(editTx.shares) * Number(editTx.price)),
    fee: String(editTx.fee),
    currency: editTx.currency,
    exchange_rate: String(editTx.exchange_rate),
  } : {
    type: initialType, date: new Date().toISOString().slice(0, 10),
    shares: '', price: '', amount: '', fee: '0', currency: 'EUR', exchange_rate: '1',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [rateStatus, setRateStatus] = useState('idle') // 'idle'|'fetching'|'auto'|'not_found'

  // Auto-rellenar tipo de cambio cuando la divisa no es EUR y cambia la fecha
  useEffect(() => {
    if (form.currency === 'EUR' || !form.date) return
    setRateStatus('fetching')
    api.get(`/markets/exchange-rate?date=${form.date}&currency=${form.currency}`)
      .then(data => {
        if (data?.rate != null) {
          setForm(f => ({ ...f, exchange_rate: String(data.rate) }))
          setRateStatus('auto')
        } else {
          setRateStatus('not_found')
        }
      })
      .catch(() => setRateStatus('not_found'))
  }, [form.date, form.currency])

  function field(name) {
    return { value: form[name], onChange: e => setForm(f => ({ ...f, [name]: e.target.value })) }
  }

  async function submit(e) {
    e.preventDefault()
    const errs = []
    if (Number(form.shares) <= 0) errs.push(t('sd.tx_err_shares'))
    // En fondos el usuario introduce el importe total; el precio por
    // participación se deriva (precio = importe / participaciones).
    const price = isFund
      ? (Number(form.shares) > 0 ? Number(form.amount) / Number(form.shares) : 0)
      : Number(form.price)
    if (isFund) {
      if (Number(form.amount) <= 0) errs.push(t('sd.tx_err_amount'))
    } else {
      if (Number(form.price) <= 0) errs.push(t('sd.tx_err_price'))
    }
    if (Number(form.exchange_rate) <= 0) errs.push(t('sd.tx_err_rate'))
    if (errs.length) { setError(errs.join('. ')); return }
    setBusy(true); setError(null)
    try {
      const payload = {
        type: form.type,
        date: form.date,
        shares: Number(form.shares),
        price: price,
        fee: Number(form.fee),
        currency: form.currency,
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
        <h2>{editTx ? t('sd.tx_modal_edit') : t('sd.tx_modal_add')}</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.tx_type')}</label>
              <select {...field('type')}>
                <option value="buy">{t('sd.tx_buy')}</option>
                <option value="sell">{t('sd.tx_sell')}</option>
              </select>
            </div>
            <div className="form-group" style={{ flex: 2 }}>
              <label>{t('sd.tx_date')}</label>
              <input type="date" {...field('date')} />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{isFund ? t('sd.tx_units') : t('sd.tx_shares')}</label>
              <input type="number" step="any" min="0.000001" {...field('shares')} required />
            </div>
            {isFund ? (
              <div className="form-group" style={{ flex: 1 }}>
                <label>{t('sd.tx_amount')}</label>
                <input type="number" step="any" min="0.000001" {...field('amount')} required />
                {Number(form.shares) > 0 && Number(form.amount) > 0 && (
                  <small style={{ color: 'var(--text-muted)' }}>
                    {t('sd.tx_price')}: {fmt(Number(form.amount) / Number(form.shares), 4)}
                  </small>
                )}
              </div>
            ) : (
              <div className="form-group" style={{ flex: 1 }}>
                <label>{t('sd.tx_price')}</label>
                <input type="number" step="any" min="0.000001" {...field('price')} required />
              </div>
            )}
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.tx_fee')}</label>
              <input type="number" step="any" min="0" {...field('fee')} />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.tx_currency')}</label>
              <select {...field('currency')}>
                {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.tx_exchange_rate')}{form.currency !== 'EUR' ? ` (EUR/${form.currency})` : ''}</label>
              <input type="number" step="any" min="0.000001" {...field('exchange_rate')}
                onChange={e => { setRateStatus('idle'); setForm(f => ({ ...f, exchange_rate: e.target.value })) }} />
              {form.currency !== 'EUR' && rateStatus === 'fetching' && (
                <small style={{ color: 'var(--text-muted)' }}>{t('sd.rate_fetching')}</small>
              )}
              {form.currency !== 'EUR' && rateStatus === 'auto' && (
                <small style={{ color: 'var(--green)' }}>✓ {t('sd.rate_auto')}</small>
              )}
              {form.currency !== 'EUR' && rateStatus === 'not_found' && (
                <small style={{ color: 'var(--text-muted)' }}>{t('sd.rate_not_found')}</small>
              )}
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>{t('common.cancel')}</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? t('sd.saving') : t('common.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function TransferModal({ originPositionId, originSecurityId, currentShares, onClose, onDone }) {
  const { t } = useAppConfig()
  const [funds, setFunds] = useState([])
  const [form, setForm] = useState({
    dest_security_id: '',
    shares: currentShares != null ? String(currentShares) : '',
    dest_shares: '',
    date: new Date().toISOString().slice(0, 10),
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  // Cargar fondos de destino: securities cuyo mercado es de fondos, excluyendo el origen
  useEffect(() => {
    Promise.all([
      api.get('/markets/list').catch(() => []),
      api.get('/securities').catch(() => []),
    ]).then(([markets, secs]) => {
      const fundCodes = new Set(markets.filter(m => m.is_fund_market).map(m => m.code))
      setFunds(secs.filter(s => fundCodes.has(s.market) && s.id !== originSecurityId))
    })
  }, [originSecurityId])

  function field(name) {
    return { value: form[name], onChange: e => setForm(f => ({ ...f, [name]: e.target.value })) }
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.dest_security_id) { setError(t('sd.transfer_err_dest')); return }
    if (Number(form.shares) <= 0 || Number(form.dest_shares) <= 0) { setError(t('sd.transfer_err_shares')); return }
    setBusy(true); setError(null)
    try {
      await api.post('/portfolio/transfer', {
        origin_position_id: originPositionId,
        shares: Number(form.shares),
        dest_security_id: Number(form.dest_security_id),
        dest_shares: Number(form.dest_shares),
        date: form.date,
      })
      onDone()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>{t('sd.transfer_modal_title')}</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: -4 }}>
          {t('sd.transfer_help')}
        </p>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>{t('sd.transfer_dest')}</label>
            <select {...field('dest_security_id')} required>
              <option value="">{t('sd.transfer_dest_ph')}</option>
              {funds.map(s => <option key={s.id} value={s.id}>{s.name} ({s.yahoo_ticker})</option>)}
            </select>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.transfer_shares_out')}</label>
              <input type="number" step="any" min="0.000001" {...field('shares')} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.transfer_shares_in')}</label>
              <input type="number" step="any" min="0.000001" {...field('dest_shares')} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.tx_date')}</label>
              <input type="date" {...field('date')} />
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>{t('common.cancel')}</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? t('sd.saving') : t('sd.transfer_submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function RecurringBuyModal({ positionId, currency, onClose, onDone }) {
  const { t } = useAppConfig()
  const _today = new Date()
  const _inAYear = new Date(_today); _inAYear.setFullYear(_today.getFullYear() + 1)
  const [form, setForm] = useState({
    amount_per_period: '',
    fee_per_period: '0',
    frequency: 'monthly',
    start_date: _today.toISOString().slice(0, 10),
    end_date: _inAYear.toISOString().slice(0, 10),
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  function field(name) {
    return { value: form[name], onChange: e => setForm(f => ({ ...f, [name]: e.target.value })) }
  }

  async function submit(e) {
    e.preventDefault()
    if (Number(form.amount_per_period) <= 0) { setError(t('sd.rec_err_amount')); return }
    if (form.end_date < form.start_date) { setError(t('sd.rec_err_end')); return }
    setBusy(true); setError(null)
    try {
      const res = await api.post(`/portfolio/${positionId}/recurring-buys`, {
        amount_per_period: Number(form.amount_per_period),
        fee_per_period: Number(form.fee_per_period || 0),
        frequency: form.frequency,
        start_date: form.start_date,
        end_date: form.end_date,
      })
      setResult(res)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>{t('sd.rec_modal_title')}</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: -4 }}>
          {t('sd.rec_help')}
        </p>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}

        {result ? (
          <div>
            <div className="state-ok" style={{ padding: 10, marginBottom: 12 }}>
              {t('sd.rec_created')}: <strong>{result.created}</strong>
              {result.created > 0 && <> · {t('sd.rec_invested')}: <strong>{fmt(result.total_invested_native)} {currency}</strong> · {fmt(result.total_shares, 4)} {t('sd.rec_units')}</>}
            </div>
            {result.plan && (
              <div className="state-ok" style={{ padding: 10, marginBottom: 12 }}>
                {t('sd.rec_plan_created')}: <strong>{result.plan.remaining}</strong> {t('sd.rec_units_left')} · {t('sd.rec_next')}: <strong>{result.plan.next_date}</strong>
              </div>
            )}
            {result.skipped?.length > 0 && (
              <div className="table-wrap" style={tableScrollStyle(result.skipped.length)}>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{t('sd.rec_skipped')}: {result.skipped.length}</p>
                <table>
                  <thead><tr><th>{t('sd.col_date')}</th><th>{t('sd.rec_reason')}</th></tr></thead>
                  <tbody>
                    {result.skipped.map((s, i) => (
                      <tr key={i}><td>{s.date}</td><td>{s.reason}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="modal-actions">
              <button type="button" className="btn-primary" onClick={onDone}>{t('common.close')}</button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit}>
            <div className="card-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>{t('sd.rec_amount')} ({currency})</label>
                <input type="number" step="any" min="0.01" {...field('amount_per_period')} required />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>{t('sd.rec_fee')} ({currency})</label>
                <input type="number" step="any" min="0" {...field('fee_per_period')} />
              </div>
            </div>
            <div className="card-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>{t('sd.rec_frequency')}</label>
                <select {...field('frequency')}>
                  <option value="weekly">{t('sd.rec_weekly')}</option>
                  <option value="monthly">{t('sd.rec_monthly')}</option>
                  <option value="quarterly">{t('sd.rec_quarterly')}</option>
                  <option value="yearly">{t('sd.rec_yearly')}</option>
                </select>
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>{t('sd.rec_start')}</label>
                <input type="date" {...field('start_date')} />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>{t('sd.rec_end')}</label>
                <input type="date" {...field('end_date')} required />
              </div>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn-ghost" onClick={onClose}>{t('common.cancel')}</button>
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? t('sd.saving') : t('sd.rec_submit')}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

function AddDivModal({ positionId, onClose, onAdded, editDiv = null, currentShares = null }) {
  const { t, currencies: CURRENCIES } = useAppConfig()
  const [form, setForm] = useState(editDiv ? {
    date: editDiv.date,
    shares_at_date: String(editDiv.shares_at_date),
    gross_per_share: String(editDiv.gross_per_share),
    gross_amount: String(editDiv.gross_amount),
    withholding_tax: String(editDiv.withholding_tax ?? '0'),
    currency: editDiv.currency,
    exchange_rate: String(editDiv.exchange_rate),
  } : {
    date: new Date().toISOString().slice(0, 10),
    shares_at_date: currentShares != null ? String(currentShares) : '',
    gross_per_share: '',
    gross_amount: '',
    withholding_tax: '0',
    currency: 'EUR', exchange_rate: '1',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [firstBracket, setFirstBracket] = useState(null)
  const [rateStatus, setRateStatus] = useState('idle')

  useEffect(() => {
    api.get('/config/tax-brackets')
      .then(data => { if (data?.length) setFirstBracket(data[0]) })
      .catch(() => {})
  }, [])

  // Auto-rellenar tipo de cambio cuando la divisa no es EUR y cambia la fecha
  useEffect(() => {
    if (form.currency === 'EUR' || !form.date) return
    setRateStatus('fetching')
    api.get(`/markets/exchange-rate?date=${form.date}&currency=${form.currency}`)
      .then(data => {
        if (data?.rate != null) {
          setForm(f => ({ ...f, exchange_rate: String(data.rate) }))
          setRateStatus('auto')
        } else {
          setRateStatus('not_found')
        }
      })
      .catch(() => setRateStatus('not_found'))
  }, [form.date, form.currency])

  // Cálculo bidireccional: shares × per_share ↔ gross_amount
  function onSharesChange(val) {
    setForm(f => {
      const shares = parseFloat(val)
      const perShare = parseFloat(f.gross_per_share)
      const gross = parseFloat(f.gross_amount)
      if (!isNaN(shares) && shares > 0 && !isNaN(perShare) && perShare > 0) {
        return { ...f, shares_at_date: val, gross_amount: (shares * perShare).toFixed(4) }
      }
      if (!isNaN(shares) && shares > 0 && !isNaN(gross) && gross > 0) {
        return { ...f, shares_at_date: val, gross_per_share: (gross / shares).toFixed(6) }
      }
      return { ...f, shares_at_date: val }
    })
  }

  function onPerShareChange(val) {
    setForm(f => {
      const perShare = parseFloat(val)
      const shares = parseFloat(f.shares_at_date)
      if (!isNaN(perShare) && perShare > 0 && !isNaN(shares) && shares > 0) {
        return { ...f, gross_per_share: val, gross_amount: (shares * perShare).toFixed(4) }
      }
      return { ...f, gross_per_share: val }
    })
  }

  function onGrossChange(val) {
    setForm(f => {
      const gross = parseFloat(val)
      const shares = parseFloat(f.shares_at_date)
      if (!isNaN(gross) && gross > 0 && !isNaN(shares) && shares > 0) {
        return { ...f, gross_amount: val, gross_per_share: (gross / shares).toFixed(6) }
      }
      return { ...f, gross_amount: val }
    })
  }

  function applyWithholding() {
    if (!firstBracket || !form.gross_amount) return
    const wh = (parseFloat(form.gross_amount) * parseFloat(firstBracket.rate) / 100).toFixed(2)
    setForm(f => ({ ...f, withholding_tax: wh }))
  }

  function field(name) {
    return { value: form[name], onChange: e => setForm(f => ({ ...f, [name]: e.target.value })) }
  }

  async function submit(e) {
    e.preventDefault()
    const errs = []
    const shares = Number(form.shares_at_date)
    const perShare = Number(form.gross_per_share)
    const gross = Number(form.gross_amount)
    if (shares <= 0) errs.push(t('sd.div_err_shares'))
    if (perShare <= 0) errs.push(t('sd.div_err_per_share'))
    if (gross <= 0) errs.push(t('sd.div_err_total'))
    if (Number(form.exchange_rate) <= 0) errs.push(t('sd.div_err_rate'))
    if (Number(form.withholding_tax) < 0) errs.push(t('sd.div_err_total'))
    // Coherencia: shares × per_share debe coincidir con gross_amount (tolerancia 1 céntimo)
    if (shares > 0 && perShare > 0 && gross > 0 && Math.abs(shares * perShare - gross) > 0.01) {
      errs.push(t('sd.div_err_coherence'))
    }
    if (errs.length) { setError(errs.join('. ')); return }
    setBusy(true); setError(null)
    try {
      const payload = {
        ...form,
        shares_at_date: shares,
        gross_per_share: perShare,
        gross_amount: gross,
        withholding_tax: Number(form.withholding_tax) || 0,
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
        <h2>{editDiv ? t('sd.div_modal_edit') : t('sd.div_modal_add')}</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.tx_date')}</label>
              <input type="date" {...field('date')} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.div_shares_at_date')}</label>
              <input type="number" step="any" min="0.000001"
                value={form.shares_at_date}
                onChange={e => onSharesChange(e.target.value)} required />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.div_per_share')}</label>
              <input type="number" step="any" min="0.000001"
                value={form.gross_per_share}
                onChange={e => onPerShareChange(e.target.value)} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.div_total_gross')}</label>
              <input type="number" step="any" min="0.000001"
                value={form.gross_amount}
                onChange={e => onGrossChange(e.target.value)} required />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.div_withholding_tax')}</label>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input type="number" step="any" min="0" style={{ flex: 1 }} {...field('withholding_tax')} />
                {firstBracket && (
                  <button type="button" className="btn-ghost btn-sm" onClick={applyWithholding}>
                    {t('sd.div_apply_rate')} -{Number(firstBracket.rate)}%
                  </button>
                )}
              </div>
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.tx_currency')}</label>
              <select {...field('currency')}>
                {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.tx_exchange_rate')}{form.currency !== 'EUR' ? ` (EUR/${form.currency})` : ''}</label>
              <input type="number" step="any" min="0.000001" {...field('exchange_rate')}
                onChange={e => { setRateStatus('idle'); setForm(f => ({ ...f, exchange_rate: e.target.value })) }} />
              {form.currency !== 'EUR' && rateStatus === 'fetching' && (
                <small style={{ color: 'var(--text-muted)' }}>{t('sd.rate_fetching')}</small>
              )}
              {form.currency !== 'EUR' && rateStatus === 'auto' && (
                <small style={{ color: 'var(--green)' }}>✓ {t('sd.rate_auto')}</small>
              )}
              {form.currency !== 'EUR' && rateStatus === 'not_found' && (
                <small style={{ color: 'var(--text-muted)' }}>{t('sd.rate_not_found')}</small>
              )}
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>{t('common.cancel')}</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? t('sd.saving') : t('common.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function EditSecurityModal({ security, onClose, onSaved }) {
  const { t, currencies: CURRENCIES } = useAppConfig()
  const [form, setForm] = useState({
    name:          security.name,
    isin:          security.isin          ?? '',
    yahoo_ticker:  security.yahoo_ticker,
    google_ticker: security.google_ticker ?? '',
    market:        security.market,
    currency:      security.currency,
  })
  const [markets, setMarkets] = useState([])
  const [busy, setBusy]   = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/markets/list').then(mks => setMarkets(mks)).catch(() => {})
  }, [])

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
        <h2>{t('sd.sec_modal_title')}</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="card-row">
            <div className="form-group" style={{ flex: 2 }}>
              <label>{t('sd.sec_name')}</label>
              <input type="text" {...field('name')} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.sec_isin')}</label>
              <input type="text" {...field('isin')} />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.sec_yahoo')}</label>
              <input type="text" {...field('yahoo_ticker')} required />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.sec_google')}</label>
              <input type="text" {...field('google_ticker')} />
            </div>
          </div>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.sec_market')}</label>
              <select {...field('market')}>
                {markets.map(m => <option key={m.code} value={m.code}>{m.name}</option>)}
              </select>
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('sd.sec_currency')}</label>
              <select {...field('currency')}>
                {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>{t('common.cancel')}</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? t('sd.saving') : t('sd.btn_save_refresh')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function SecurityDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { t } = useAppConfig()
  const { user } = useAuth()
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
  const [showTransfer, setShowTransfer] = useState(false)
  const [showRecurring, setShowRecurring] = useState(false)
  const [plans, setPlans] = useState([])
  const [isFundMarket, setIsFundMarket] = useState(false)
  const [editingNotes, setEditingNotes] = useState(false)
  const [notesVal, setNotesVal]         = useState('')
  const [targetBuyVal, setTargetBuyVal] = useState('')
  const [targetSellVal, setTargetSellVal] = useState('')
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
      const [sec, snap, hist, posResult, favs, markets] = await Promise.all([
        api.get(`/securities/${secId}`),
        api.get(`/markets/${secId}/snapshot`).catch(() => null),
        api.get(`/markets/${secId}/history`).catch(() => []),
        api.get(`/portfolio/by-security/${secId}`).catch(() => null),
        api.get('/favorites'),
        api.get('/markets/list').catch(() => []),
      ])
      setSecurity(sec)
      setSnapshot(snap)
      setHistory(hist.slice(-365))
      setIsFav(favs.some(f => f.security_id === secId))
      // target_buy_price: fuente única = favorites (compartido con la lista de mercados)
      const fav = favs.find(f => f.security_id === secId)
      setTargetBuyVal(fav?.target_buy_price != null ? String(fav.target_buy_price) : '')

      // Refresco perezoso: si el valor no está "en uso" y su snapshot está
      // rancio, el backend lo actualiza ahora (anti-rebote 1 h). No entra en la
      // programación de cada N min. Si refresca, recargamos el snapshot.
      api.post(`/markets/${secId}/refresh-if-stale`)
        .then(r => { if (r?.refreshed) api.get(`/markets/${secId}/snapshot`).then(setSnapshot).catch(() => {}) })
        .catch(() => {})
      setIsFundMarket(markets.some(m => m.code === sec.market && m.is_fund_market))

      // Planes de aportación periódica activos para este valor.
      const allPlans = await api.get('/portfolio/recurring-plans').catch(() => [])
      setPlans(allPlans.filter(p => p.security_id === secId))

      // Operaciones del valor (exista o no posición abierta): así el historial
      // de compras/ventas/traspasos se ve también con la posición CERRADA.
      const ops = await api.get(`/portfolio/by-security/${secId}/operations`).catch(() => null)
      if (ops) {
        setPositionId(ops.position_id)
        setTxs(ops.transactions || [])
        setDivs(ops.dividends || [])
      }

      if (posResult) {
        // Posición abierta
        setPosResult(posResult)
        setIsClosed(false)
        setNotesVal(posResult.notes ?? '')
        // target_sell: solo tiene sentido en posición abierta (positions.target_sell_price)
        setTargetSellVal(posResult.target_sell_price != null ? String(posResult.target_sell_price) : '')
        // target_buy se inicializa arriba desde favorites (antes del if posResult)
      } else if (ops) {
        // Hay operaciones pero la posición está cerrada (vendida o traspasada).
        setIsClosed(true)
        const closedAll = await api.get('/portfolio/closed').catch(() => [])
        const closedPos = closedAll.find(p => p.security_id === secId)
        if (closedPos) setClosedSummary(closedPos)
      }
    } catch (err) { setError(err.message) }
  }

  useEffect(() => { loadAll() }, [secId])

  async function deleteTx(txId) {
    if (!confirm(t('sd.tx_confirm_delete'))) return
    setOpError(null)
    try {
      await api.delete(`/portfolio/${positionId}/transactions/${txId}`)
      setTxs(ts => ts.filter(t => t.id !== txId))
    } catch (err) { setOpError(err.message) }
  }

  async function deleteDiv(divId) {
    if (!confirm(t('sd.div_confirm_delete'))) return
    setOpError(null)
    try {
      await api.delete(`/portfolio/${positionId}/dividends/${divId}`)
      setDivs(ds => ds.filter(d => d.id !== divId))
    } catch (err) { setOpError(err.message) }
  }

  async function deleteTransfer(groupId) {
    if (!groupId) return
    if (!confirm(t('sd.transfer_confirm_delete'))) return
    setOpError(null)
    try {
      await api.delete(`/portfolio/transfer/${groupId}`)
      loadAll()  // afecta a dos posiciones: recargar el estado completo
    } catch (err) { setOpError(err.message) }
  }

  async function cancelPlan(planId) {
    if (!confirm(t('sd.rec_confirm_cancel'))) return
    setOpError(null)
    try {
      await api.delete(`/portfolio/recurring-plans/${planId}`)
      setPlans(ps => ps.filter(p => p.id !== planId))
    } catch (err) { setOpError(err.message) }
  }

  async function saveNotes() {
    setEditingNotes(false)
    try {
      await api.patch(`/portfolio/${positionId}/notes`, { notes: notesVal || null })
    } catch { /* silencioso */ }
  }

  async function saveTargetBuy(val) {
    const num = val === '' ? null : parseFloat(val)
    if (num !== null && (isNaN(num) || num < 0)) return
    try {
      // target_buy vive en favorites (fuente única, misma que la lista de mercados).
      // Si el valor aún no es favorito, lo añadimos primero.
      if (!isFav) {
        await api.post(`/favorites/${secId}`)
        setIsFav(true)
      }
      await api.patch(`/favorites/${secId}`, { target_buy_price: num })
    } catch { /* silencioso */ }
  }

  async function saveTargetSell(val) {
    const num = val === '' ? null : parseFloat(val)
    if (num !== null && (isNaN(num) || num < 0)) return
    try {
      await api.patch(`/portfolio/${positionId}/target-sell`, { target_sell_price: num })
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
  const transfers = transactions.filter(t => t.type === 'transfer_in' || t.type === 'transfer_out')

  // Ordenación de las tablas del detalle (cliente, no persistente).
  const numN = v => (v != null && v !== '' ? Number(v) : null)
  const txColumns = [
    { key: 'date',     label: t('sd.col_date'),     accessor: tx => tx.date },
    { key: 'shares',   label: t('sd.col_shares'),   className: 'num', accessor: tx => numN(tx.shares) },
    { key: 'price',    label: t('sd.col_price'),    className: 'num', accessor: tx => numN(tx.price) },
    { key: 'fee',      label: t('sd.col_fee'),      className: 'num', accessor: tx => numN(tx.fee) },
    { key: 'currency', label: t('sd.col_currency'), className: 'num', accessor: tx => tx.currency },
    { key: 'total',    label: t('sd.col_total_op'), className: 'num', accessor: tx => totalOp(tx) },
    { key: 'actions',  label: '' },
  ]
  const divColumns = [
    { key: 'date',     label: t('sd.col_date'),       accessor: d => d.date },
    { key: 'shares',   label: t('sd.col_shares'),     className: 'num', accessor: d => numN(d.shares_at_date) },
    { key: 'pershare', label: t('sd.col_per_share'),  className: 'num', accessor: d => numN(d.gross_per_share) },
    { key: 'gross',    label: t('sd.col_gross'),      className: 'num', accessor: d => numN(d.gross_amount) },
    { key: 'currency', label: t('sd.col_currency'),   className: 'num', accessor: d => d.currency },
    { key: 'actions',  label: '' },
  ]
  const transferColumns = [
    { key: 'date',      label: t('sd.col_date'),            accessor: tx => tx.date },
    { key: 'direction', label: t('sd.transfer_direction'),  accessor: tx => tx.type },
    { key: 'related',   label: t('sd.col_related_fund'),    accessor: tx => tx.related_security_name || null },
    { key: 'shares',    label: t('sd.col_shares'),          className: 'num', accessor: tx => numN(tx.shares) },
    { key: 'cost',      label: t('sd.transfer_cost'),       className: 'num', accessor: tx => Number(tx.shares) * Number(tx.price) },
    { key: 'actions',   label: '' },
  ]
  const buysSort      = useSortableData(buys)
  const sellsSort     = useSortableData(sells)
  const transfersSort = useSortableData(transfers)
  const divsSort      = useSortableData(dividends)
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
  // B/P Latente sin comisiones: se añaden las comisiones de compra ya incluidas
  // en el coste de los lotes, para mostrar solo el movimiento de precio.
  const grossUnrealizedEur = posResult
    ? Number(posResult.unrealized_pnl_eur) + totalFeesEur
    : 0
  // Beneficio realizado en posición aún abierta (ventas parciales pasadas)
  const openRealizedEur = posResult ? Number(posResult.realized_pnl_eur) : 0
  // B/P Total: latente + realizadas + dividendos - comisiones
  // = (unrealized + fees) + realized + dividends - fees = unrealized + realized + dividends
  const openBpTotalEur = posResult
    ? grossUnrealizedEur + openRealizedEur + Number(posResult.dividends_eur) - totalFeesEur
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
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {(() => {
            if (!snapshot?.last_price || !positionId) return null
            const cur = Number(snapshot.last_price)
            const buy = targetBuyVal !== '' ? Number(targetBuyVal) : null
            const sell = targetSellVal !== '' ? Number(targetSellVal) : null
            const sellAlert = sell !== null && !isNaN(sell) && sell > 0 && cur >= sell
            const buyAlert = buy !== null && !isNaN(buy) && buy > 0 && cur <= buy
            if (!sellAlert && !buyAlert) return null
            return (
              <span style={{
                color: 'var(--green, #16a34a)',
                fontWeight: 600,
                fontSize: '0.85rem',
                border: '1px solid var(--green, #16a34a)',
                borderRadius: 4,
                padding: '3px 10px',
                animation: 'priceAlertBlink 1.5s ease-in-out infinite',
              }}>
                {sellAlert ? t('sd.alert_sell') : t('sd.alert_buy')}
              </span>
            )
          })()}
          <button className="btn-ghost btn-sm" onClick={toggleFav}>
            {isFav ? t('sd.fav_remove') : t('sd.fav_add')}
          </button>
          {user?.is_admin && (
            <button className="btn-ghost btn-sm" onClick={() => setShowEditSec(true)}>{t('sd.btn_edit')}</button>
          )}
          <button className="btn-ghost btn-sm" onClick={refresh}>{t('sd.btn_refresh')}</button>
        </div>
      </div>

      {/* Snapshot */}
      {snapshot && (
        <div className="card-row">
          <div className="card small">
            <div className="value">{fmt(snapshot.last_price)} {security.currency}</div>
            <div className="label">{t('sd.price_current')}</div>
          </div>
          <div className="card small">
            <div className={`value ${pctCls}`}>
              {pct != null ? `${pct >= 0 ? '+' : ''}${fmt(pct)}%` : '—'}
            </div>
            <div className="label">{t('sd.var_day')}</div>
          </div>
          <div className="card small">
            <div className="value">{fmt(snapshot.min_1y)}</div>
            <div className="label">{t('sd.min_1y')}</div>
          </div>
          <div className="card small">
            <div className="value">{fmt(snapshot.max_1y)}</div>
            <div className="label">{t('sd.max_1y')}</div>
          </div>
        </div>
      )}

      {/* Resumen posición */}
      {(posResult || isClosed) && (
        <div className="card-row">
          <div className="card small">
            <div className="value">{posResult ? fmtShares(posResult.shares) : '0'}</div>
            <div className="label">{t('sd.shares_owned')}</div>
          </div>
          <div className="card small">
            <div className="value">{fmt(posResult ? posResult.market_value_eur : 0)} €</div>
            <div className="label">{t('sd.value_current')}</div>
          </div>
          {isClosed && closedSummary && (
            <>
              <div className="card small">
                <div className={`value ${cls(grossSaleGainEur)}`}>
                  {sign(grossSaleGainEur)}{fmt(grossSaleGainEur)} €
                </div>
                <div className="label">{t('sd.bp_sale')}</div>
              </div>
              <div className="card small">
                <div className="value">{fmt(closedSummary.dividends_eur)} €</div>
                <div className="label">{t('sd.dividends_gross')}</div>
              </div>
              <div className="card small">
                <div className="value neg">{totalFeesEur > 0 ? `-${fmt(totalFeesEur)}` : fmt(totalFeesEur)} €</div>
                <div className="label">{t('sd.fees_paid')}</div>
              </div>
              <div className="card small">
                <div className={`value ${cls(closedSummary.total_profit_eur)}`}>
                  {sign(closedSummary.total_profit_eur)}{fmt(closedSummary.total_profit_eur)} €
                </div>
                <div className="label">{t('sd.bp_total')}</div>
              </div>
            </>
          )}
          {posResult && (
            <>
              <div className="card small">
                <div className="value">{fmt(posResult.cost_eur)} €</div>
                <div className="label">{t('sd.invested')}</div>
              </div>
              <div className="card small">
                <div className="value">{fmt(posResult.avg_cost_eur)} €</div>
                <div className="label">{t('sd.avg_cost')}</div>
              </div>
              <div className="card small">
                <div className={`value ${cls(grossUnrealizedEur)}`}>
                  {sign(grossUnrealizedEur)}{fmt(grossUnrealizedEur)} €
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                  {sign(posResult.unrealized_pnl_pct)}{fmt(posResult.unrealized_pnl_pct)}%
                </div>
                <div className="label">{t('sd.bp_latent')}</div>
              </div>
              {openRealizedEur !== 0 && (
                <div className="card small">
                  <div className={`value ${cls(openRealizedEur)}`}>
                    {sign(openRealizedEur)}{fmt(openRealizedEur)} €
                  </div>
                  <div className="label">{t('sd.bp_sale')}</div>
                </div>
              )}
              <div className="card small">
                <div className="value">{fmt(posResult.dividends_eur)} €</div>
                <div className="label">{t('sd.dividends_gross')}</div>
              </div>
              <div className="card small">
                <div className="value neg">{totalFeesEur > 0 ? `-${fmt(totalFeesEur)}` : fmt(totalFeesEur)} €</div>
                <div className="label">{t('sd.fees_paid')}</div>
              </div>
              <div className="card small">
                <div className={`value ${cls(openBpTotalEur)}`}>
                  {sign(openBpTotalEur)}{fmt(openBpTotalEur)} €
                </div>
                <div className="label">{t('sd.bp_total')}</div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Notas + Precios objetivo (flex-wrap: en ancho queda en fila, en móvil en columna) */}
      {positionId && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {/* Notas */}
          <div className="card" style={{ padding: '10px 16px', flex: '2 1 260px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', minWidth: 48, paddingTop: 2 }}>{t('sd.notes')}</span>
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
                  title={t('sd.notes_click_edit')}
                  onClick={() => setEditingNotes(true)}
                >
                  {notesVal || t('sd.notes_add')}
                </span>
              )}
            </div>
          </div>

          {/* Precios objetivo */}
          <div className="card" style={{ padding: '10px 16px', flex: '1 1 200px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { label: t('sd.target_buy'), val: targetBuyVal, set: setTargetBuyVal, save: saveTargetBuy },
                { label: t('sd.target_sell'), val: targetSellVal, set: setTargetSellVal, save: saveTargetSell },
              ].map(({ label, val, set, save }) => {
                // % hasta objetivo: cuánto debe moverse el precio actual para alcanzar el objetivo.
                const price = snapshot?.last_price != null ? Number(snapshot.last_price) : null
                const target = val !== '' ? Number(val) : null
                const pctToTarget = (price != null && price > 0 && target != null && !isNaN(target))
                  ? (target - price) / price * 100
                  : null
                return (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', minWidth: 90 }}>{label}</span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={val}
                      onChange={e => set(e.target.value)}
                      onBlur={e => save(e.target.value)}
                      placeholder={t('sd.target_ph')}
                      style={{ width: 90, padding: '3px 6px', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)', fontSize: '0.85rem', fontFamily: 'var(--mono)' }}
                    />
                    {pctToTarget != null && (
                      <span
                        title={t('sd.target_pct')}
                        style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontFamily: 'var(--mono)', minWidth: 64 }}
                      >
                        {pctToTarget >= 0 ? '+' : ''}{fmt(pctToTarget)}%
                      </span>
                    )}
                    {val !== '' && (
                      <button
                        className="btn-ghost btn-sm"
                        style={{ padding: '2px 6px', fontSize: '0.75rem' }}
                        onClick={() => { set(''); save('') }}
                      >✕</button>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Gráfico */}
      {chartData.length > 0 && (
        <div className="card">
          <h2>{t('sd.chart_history')}</h2>
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
                  formatter={v => [fmt(v), t('sd.chart_price')]}
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
          <h2 style={{ marginBottom: 0 }}>{t('sd.buys')}</h2>
          {positionId
            ? (
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn-ghost btn-sm" onClick={() => setShowRecurring(true)}>{t('sd.rec_button')}</button>
                <button className="btn-primary btn-sm" onClick={() => { setTxModalType('buy'); setEditingTx(null); setTxModal(true) }}>{t('sd.btn_add')}</button>
              </div>
            )
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
                {startingTracking ? t('sd.btn_starting') : t('sd.btn_start_tracking')}
              </button>
            )
          }
        </div>
        {buys.length === 0 ? (
          <div className="state-empty" style={{ padding: 20 }}>
            {positionId ? t('sd.no_buys') : t('sd.no_buys_hint')}
          </div>
        ) : (
          <div className="table-wrap" style={tableScrollStyle(buys.length)}>
            <table>
              <SortableHead columns={txColumns} sortKey={buysSort.sortKey} sortDir={buysSort.sortDir} requestSort={buysSort.requestSort} />
              <tbody>{buysSort.sorted.map(tx => <TxRow key={tx.id} tx={tx} onDelete={deleteTx} onEdit={tx => { setEditingTx(tx); setTxModal(true) }} />)}</tbody>
            </table>
          </div>
        )}

        {/* Planes de aportación periódica activos (futuros) */}
        {plans.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <h3 style={{ marginBottom: 8, fontSize: '0.95rem' }}>{t('sd.rec_plans_title')}</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{t('sd.rec_amount')}</th>
                    <th>{t('sd.rec_frequency')}</th>
                    <th>{t('sd.rec_next')}</th>
                    <th className="num">{t('sd.rec_remaining')}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {plans.map(p => (
                    <tr key={p.id}>
                      <td>{fmt(p.amount_per_period)} {p.currency}</td>
                      <td>{t(`sd.rec_${p.frequency}`)}</td>
                      <td>{p.next_date}</td>
                      <td className="num">{p.remaining}</td>
                      <td className="num">
                        <button className="btn-ghost btn-sm" onClick={() => cancelPlan(p.id)}>{t('sd.rec_cancel')}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Ventas */}
      {(sells.length > 0 || positionId) && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ marginBottom: 0 }}>{t('sd.sells')}</h2>
            {positionId && (
              <button
                className="btn-primary btn-sm"
                onClick={() => { setTxModalType('sell'); setEditingTx(null); setTxModal(true) }}
              >
                {t('sd.btn_add')}
              </button>
            )}
          </div>
          {sells.length === 0 ? (
            <div className="state-empty" style={{ padding: 20 }}>{t('sd.no_sells')}</div>
          ) : (
            <div className="table-wrap" style={tableScrollStyle(sells.length)}>
              <table>
                <SortableHead columns={txColumns} sortKey={sellsSort.sortKey} sortDir={sellsSort.sortDir} requestSort={sellsSort.requestSort} />
                <tbody>{sellsSort.sorted.map(tx => <TxRow key={tx.id} tx={tx} onDelete={deleteTx} onEdit={tx => { setEditingTx(tx); setTxModal(true) }} />)}</tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Traspasos (solo fondos) */}
      {isFundMarket && (positionId || transfers.length > 0) && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ marginBottom: 0 }}>{t('sd.transfers')}</h2>
            {positionId && (
              <button className="btn-primary btn-sm" onClick={() => setShowTransfer(true)}>
                {t('sd.transfer_new')}
              </button>
            )}
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: 0 }}>
            {t('sd.transfer_note')}
          </p>
          {/* Rentabilidad propia del fondo desde el traspaso (solo si la posición
              se nutre únicamente de traspasos: sin compras ni ventas). Distinta del
              B/P latente, que arrastra la base de coste heredada. */}
          {posResult?.transfer_in_market_eur > 0 && buys.length === 0 && sells.length === 0 && (() => {
            const tin = Number(posResult.transfer_in_market_eur)
            const now = Number(posResult.market_value_eur)
            const pct = tin > 0 ? (now / tin - 1) * 100 : 0
            return (
              <div className="state-ok" style={{ padding: 10, marginBottom: 12, textAlign: 'left' }}>
                {t('sd.transfer_since')}: <strong className={pct >= 0 ? 'pos' : 'neg'}>{pct >= 0 ? '+' : ''}{fmt(pct)}%</strong>
                <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>
                  ({t('sd.transfer_value_at')}: {fmt(tin)} € → {fmt(now)} €)
                </span>
              </div>
            )
          })()}
          {transfers.length === 0 ? (
            <div className="state-empty" style={{ padding: 20 }}>{t('sd.no_transfers')}</div>
          ) : (
            <div className="table-wrap" style={tableScrollStyle(transfers.length)}>
              <table>
                <SortableHead columns={transferColumns} sortKey={transfersSort.sortKey} sortDir={transfersSort.sortDir} requestSort={transfersSort.requestSort} />
                <tbody>
                  {transfersSort.sorted.map(tx => (
                    <tr key={tx.id}>
                      <td>{tx.date}</td>
                      <td>{tx.type === 'transfer_in' ? `↓ ${t('sd.transfer_in')}` : `↑ ${t('sd.transfer_out')}`}</td>
                      <td>
                        {tx.related_security_id ? (
                          <a
                            href={`/securities/${tx.related_security_id}`}
                            style={{ color: 'var(--accent)', textDecoration: 'none', fontSize: '0.85rem' }}
                            onClick={e => { e.preventDefault(); navigate(`/securities/${tx.related_security_id}`) }}
                          >
                            {tx.related_security_name}
                          </a>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>—</span>
                        )}
                      </td>
                      <td className="num">{fmtShares(tx.shares)}</td>
                      <td className="num">{fmt(Number(tx.shares) * Number(tx.price))} €</td>
                      <td className="num">
                        {tx.transfer_group_id && (
                          <button
                            className="btn-ghost btn-sm"
                            title={t('sd.transfer_undo')}
                            onClick={() => deleteTransfer(tx.transfer_group_id)}
                          >
                            {t('sd.transfer_undo')}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Dividendos */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h2 style={{ marginBottom: 0 }}>
            {t('sd.dividends')}
            {totalDivsGross > 0 && (
              <span style={{ marginLeft: 10, fontSize: '0.85rem', color: 'var(--green)', fontFamily: 'var(--mono)' }}>
                +{fmt(totalDivsGross)} €
              </span>
            )}
          </h2>
          {positionId && (
            <button className="btn-ghost btn-sm" onClick={() => { setEditingDiv(null); setDivModal(true) }}>{t('sd.btn_add')}</button>
          )}
        </div>
        {dividends.length === 0 ? (
          <div className="state-empty" style={{ padding: 20 }}>{t('sd.no_dividends')}</div>
        ) : (
          <div className="table-wrap" style={tableScrollStyle(dividends.length)}>
            <table>
              <SortableHead columns={divColumns} sortKey={divsSort.sortKey} sortDir={divsSort.sortDir} requestSort={divsSort.requestSort} />
              <tbody>{divsSort.sorted.map(d => <DivRow key={d.id} div={d} onDelete={deleteDiv} onEdit={d => { setEditingDiv(d); setDivModal(true) }} />)}</tbody>
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
          isFund={isFundMarket}
          onClose={() => { setTxModal(false); setEditingTx(null) }}
          onAdded={() => { setTxModal(false); setEditingTx(null); loadAll() }}
        />
      )}
      {showDivModal && (
        <AddDivModal
          positionId={positionId}
          editDiv={editingDiv}
          currentShares={posResult?.shares ?? null}
          onClose={() => { setDivModal(false); setEditingDiv(null) }}
          onAdded={() => { setDivModal(false); setEditingDiv(null); loadAll() }}
        />
      )}
      {showTransfer && (
        <TransferModal
          originPositionId={positionId}
          originSecurityId={secId}
          currentShares={posResult?.shares ?? null}
          onClose={() => setShowTransfer(false)}
          onDone={() => { setShowTransfer(false); loadAll() }}
        />
      )}
      {showRecurring && (
        <RecurringBuyModal
          positionId={positionId}
          currency={security.currency}
          onClose={() => setShowRecurring(false)}
          onDone={() => { setShowRecurring(false); loadAll() }}
        />
      )}
    </div>
  )
}
