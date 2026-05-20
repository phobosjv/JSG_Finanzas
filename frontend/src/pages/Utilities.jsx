import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

const MARKETS   = ['ibex35', 'continuo', 'nasdaq']
const CURRENCIES = ['EUR', 'USD']

const EMPTY_FORM = {
  name: '', isin: '', yahoo_ticker: '', google_ticker: '',
  market: 'ibex35', currency: 'EUR',
}

export default function Utilities() {
  const [securities, setSecurities] = useState(null)
  const [form, setForm]             = useState(EMPTY_FORM)
  const [showForm, setShowForm]     = useState(false)
  const [editingSec, setEditingSec] = useState(null)  // security being edited
  const [busy, setBusy]             = useState(false)
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [error, setError]           = useState(null)
  const [success, setSuccess]       = useState(null)

  // Informe fiscal
  const currentYear = new Date().getFullYear()
  const [taxYear, setTaxYear]       = useState(currentYear - 1)
  const [taxBusy, setTaxBusy]       = useState(false)

  // Backup
  const [importing, setImporting]   = useState(false)
  const [backupMsg, setBackupMsg]   = useState(null)
  const [backupErr, setBackupErr]   = useState(null)
  const fileRef                     = useRef(null)

  async function load() {
    const secs = await api.get('/securities')
    setSecurities(secs)
  }

  useEffect(() => { load() }, [])

  function field(name) {
    return {
      value: form[name],
      onChange: e => setForm(f => ({ ...f, [name]: e.target.value })),
    }
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null); setSuccess(null)
    try {
      const body = { ...form }
      if (!body.isin) delete body.isin
      if (!body.google_ticker) delete body.google_ticker
      if (editingSec) {
        await api.patch(`/securities/${editingSec.id}`, body)
        setEditingSec(null)
        setSuccess('Valor actualizado correctamente')
      } else {
        await api.post('/securities', body)
        setSuccess('Valor añadido correctamente')
      }
      setForm(EMPTY_FORM)
      setShowForm(false)
      await load()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  function startEdit(s) {
    setEditingSec(s)
    setForm({ name: s.name, isin: s.isin ?? '', yahoo_ticker: s.yahoo_ticker, google_ticker: s.google_ticker ?? '', market: s.market, currency: s.currency })
    setShowForm(true)
    setError(null)
    setSuccess(null)
  }

  async function refreshAll() {
    setRefreshBusy(true); setSuccess(null); setError(null)
    try {
      const res = await api.post('/markets/refresh-all')
      setSuccess(res.detail)
    } catch (err) { setError(err.message) }
    finally { setRefreshBusy(false) }
  }

  async function downloadTaxReport() {
    setTaxBusy(true)
    try {
      const res = await fetch(`/api/reports/tax/${taxYear}`, { credentials: 'include' })
      if (!res.ok) { alert(`Error al generar el informe: ${res.status}`); return }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `informe_fiscal_${taxYear}.pdf`; a.click()
      URL.revokeObjectURL(url)
    } finally { setTaxBusy(false) }
  }

  async function exportBackup() {
    const res = await fetch('/api/backup/export', { credentials: 'include' })
    if (!res.ok) { setBackupErr('Error al exportar'); return }
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') ?? ''
    const match = cd.match(/filename="([^"]+)"/)
    const filename = match ? match[1] : 'finanzas_backup.json'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  async function importBackup(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true); setBackupMsg(null); setBackupErr(null)
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const result = await api.post('/backup/import', data)
      setBackupMsg(
        `Importado: ${result.positions_found} posiciones, ` +
        `${result.transactions_added} transacciones, ` +
        `${result.dividends_added} dividendos.` +
        (result.errors.length ? ` Avisos: ${result.errors.join(' ')}` : '')
      )
    } catch (err) { setBackupErr(err.message) }
    finally { setImporting(false); e.target.value = '' }
  }

  async function del(id, ticker) {
    if (!confirm(`¿Eliminar ${ticker}? Solo es posible si no tiene histórico.`)) return
    try {
      await api.delete(`/securities/${id}`)
      await load()
    } catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1>Catálogo de valores</h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn-ghost btn-sm"
            disabled={refreshBusy}
            onClick={refreshAll}
            title="Actualiza el histórico y el snapshot de todos los valores"
          >
            {refreshBusy ? 'Actualizando…' : '↺ Actualizar todo'}
          </button>
          <button className="btn-primary btn-sm" onClick={() => {
            setEditingSec(null)
            setForm(EMPTY_FORM)
            setShowForm(s => !s)
            setError(null)
            setSuccess(null)
          }}>
            {showForm ? 'Cancelar' : '+ Nuevo valor'}
          </button>
        </div>
      </div>

      {error   && <div className="state-error"   style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
      {success && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>{success}</div>}

      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2>{editingSec ? 'Editar valor' : 'Nuevo valor'}</h2>
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
                <input type="text" {...field('yahoo_ticker')} required placeholder="p.ej. AAPL, SAN.MC" />
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
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? 'Guardando…' : 'Guardar'}
              </button>
            </div>
          </form>
        </div>
      )}

      {securities === null ? (
        <div className="state-loading"><div className="spinner" /></div>
      ) : securities.length === 0 ? (
        <div className="state-empty">No hay valores en el catálogo. Añade el primero.</div>
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Nombre</th>
                  <th>ISIN</th>
                  <th>Mercado</th>
                  <th>Divisa</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {securities.map(s => (
                  <tr key={s.id}>
                    <td className="ticker">{s.yahoo_ticker}</td>
                    <td>{s.name}</td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{s.isin ?? '—'}</td>
                    <td><span className="badge badge-market">{s.market}</span></td>
                    <td>{s.currency}</td>
                    <td style={{ display: 'flex', gap: 4 }}>
                      <button className="btn-ghost btn-sm" onClick={() => startEdit(s)}>✎</button>
                      <button className="btn-danger btn-sm" onClick={() => del(s.id, s.yahoo_ticker)}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Informe fiscal */}
      <div className="card" style={{ marginTop: 24 }}>
        <h2>Informe fiscal (IRPF)</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: '0.9rem' }}>
          Genera un PDF con las operaciones de compra/venta del año seleccionado,
          el beneficio o pérdida de cada valor y un resumen para la declaración de la renta.
        </p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <select
              value={taxYear}
              onChange={e => setTaxYear(Number(e.target.value))}
              style={{ width: 'auto' }}
            >
              {Array.from({ length: 10 }, (_, i) => currentYear - 1 - i).map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
          <button
            className="btn-primary btn-sm"
            disabled={taxBusy}
            onClick={downloadTaxReport}
          >
            {taxBusy ? 'Generando…' : '↓ Descargar PDF'}
          </button>
        </div>
      </div>

      {/* Backup */}
      <div className="card" style={{ marginTop: 24 }}>
        <h2>Copia de seguridad</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: '0.9rem' }}>
          Exporta todas tus posiciones, transacciones y dividendos a un fichero JSON.
          La importación es idempotente: no duplica registros ya existentes.
        </p>

        {backupErr && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{backupErr}</div>}
        {backupMsg && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>{backupMsg}</div>}

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <button className="btn-primary btn-sm" onClick={exportBackup}>
            ↓ Exportar JSON
          </button>
          <button
            className="btn-ghost btn-sm"
            disabled={importing}
            onClick={() => fileRef.current?.click()}
          >
            {importing ? 'Importando…' : '↑ Importar JSON'}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".json,application/json"
            style={{ display: 'none' }}
            onChange={importBackup}
          />
        </div>
      </div>
    </div>
  )
}
