import { useRef, useState } from 'react'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'

// ---------------------------------------------------------------------------
//  Parseo de CSV en el cliente (sin dependencias externas)
// ---------------------------------------------------------------------------

function parseCsv(text) {
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
  const nonEmpty = lines.filter(l => l.trim() !== '')
  if (nonEmpty.length < 2) return []
  const headers = nonEmpty[0].split(',').map(h => h.trim().toLowerCase())
  return nonEmpty.slice(1).map((line, i) => {
    const vals = line.split(',').map(v => v.trim())
    const obj = { _row: i + 2 }  // 1-based, +1 para la cabecera
    headers.forEach((h, j) => { obj[h] = vals[j] ?? '' })
    return obj
  })
}

function rowHasError(row) {
  if (!row.type || !['buy', 'sell', 'dividend'].includes(row.type)) return true
  if (!row.ticker) return true
  if (!row.date) return true
  if (!row.shares || isNaN(Number(row.shares))) return true
  if ((row.type === 'buy' || row.type === 'sell') && (!row.price || isNaN(Number(row.price)))) return true
  if (row.type === 'dividend' && (!row.gross_per_share || isNaN(Number(row.gross_per_share)))) return true
  return false
}

const TYPE_COLORS = { buy: 'var(--green)', sell: 'var(--red)', dividend: 'var(--accent)' }

export default function Utilities() {
  const { theme, toggleTheme, locale, setLocale, t } = useAppConfig()

  // Cambio de contraseña
  const [pwForm, setPwForm] = useState({ current: '', newPw: '', confirm: '' })
  const [pwBusy, setPwBusy] = useState(false)
  const [pwError, setPwError] = useState(null)
  const [pwOk, setPwOk]     = useState(false)

  // Backup
  const [importing, setImporting]   = useState(false)
  const [backupMsg, setBackupMsg]   = useState(null)
  const [backupErr, setBackupErr]   = useState(null)
  const fileRef                     = useRef(null)

  // CSV import
  const csvFileRef                      = useRef(null)
  const [csvRows, setCsvRows]           = useState(null)   // null = nada cargado
  const [csvParseErr, setCsvParseErr]   = useState(null)
  const [csvImporting, setCsvImporting] = useState(false)
  const [csvResult, setCsvResult]       = useState(null)
  const [csvErr, setCsvErr]             = useState(null)

  function onCsvFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setCsvRows(null); setCsvParseErr(null); setCsvResult(null); setCsvErr(null)
    const reader = new FileReader()
    reader.onload = ev => {
      try {
        const rows = parseCsv(ev.target.result)
        if (rows.length === 0) { setCsvParseErr(t('utilities.csv_no_rows')); return }
        setCsvRows(rows)
      } catch {
        setCsvParseErr(t('utilities.csv_parse_error'))
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  async function importCsv() {
    if (!csvRows?.length) return
    setCsvImporting(true); setCsvResult(null); setCsvErr(null)
    try {
      const rows = csvRows.map(r => ({
        type: r.type,
        ticker: (r.ticker || '').toUpperCase(),
        date: r.date,
        shares: Number(r.shares),
        price: r.price ? Number(r.price) : undefined,
        gross_per_share: r.gross_per_share ? Number(r.gross_per_share) : undefined,
        gross_amount: r.gross_amount ? Number(r.gross_amount) : undefined,
        fee: r.fee ? Number(r.fee) : 0,
        withholding_tax: r.withholding_tax ? Number(r.withholding_tax) : 0,
        currency: r.currency || 'EUR',
        exchange_rate: r.exchange_rate ? Number(r.exchange_rate) : 1,
      }))
      const result = await api.post('/portfolio/import-csv', { rows })
      setCsvResult(result)
      setCsvRows(null)
    } catch (err) { setCsvErr(err.message) }
    finally { setCsvImporting(false) }
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

  async function changePassword(e) {
    e.preventDefault()
    setPwError(null); setPwOk(false)
    if (pwForm.newPw.length < 8) { setPwError('La nueva contraseña debe tener al menos 8 caracteres'); return }
    if (pwForm.newPw !== pwForm.confirm) { setPwError('Las contraseñas no coinciden'); return }
    setPwBusy(true)
    try {
      await api.patch('/auth/password', { current_password: pwForm.current, new_password: pwForm.newPw })
      setPwForm({ current: '', newPw: '', confirm: '' })
      setPwOk(true)
    } catch (err) { setPwError(err.message) }
    finally { setPwBusy(false) }
  }

  return (
    <div>
      <h1>{t('utilities.title')}</h1>

      {/* Cambiar contraseña */}
      <div className="card">
        <h2>{t('utilities.password')}</h2>
        {pwError && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{pwError}</div>}
        {pwOk    && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>{t('utilities.pw_ok')}</div>}
        <form onSubmit={changePassword}>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('utilities.pw_current')}</label>
              <input
                type="password"
                value={pwForm.current}
                onChange={e => setPwForm(f => ({ ...f, current: e.target.value }))}
                required
              />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('utilities.pw_new')}</label>
              <input
                type="password"
                value={pwForm.newPw}
                onChange={e => setPwForm(f => ({ ...f, newPw: e.target.value }))}
                required
                minLength={8}
              />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>{t('utilities.pw_confirm')}</label>
              <input
                type="password"
                value={pwForm.confirm}
                onChange={e => setPwForm(f => ({ ...f, confirm: e.target.value }))}
                required
              />
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button type="submit" className="btn-primary btn-sm" disabled={pwBusy}>
              {pwBusy ? t('utilities.pw_saving') : t('utilities.pw_save')}
            </button>
          </div>
        </form>
      </div>

      {/* Tema */}
      <div className="card" style={{ marginTop: 24 }}>
        <h2>{t('utilities.appearance')}</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            {t('utilities.theme_current')}{' '}
            <strong style={{ color: 'var(--text)' }}>
              {theme === 'dark' ? t('utilities.theme_dark') : t('utilities.theme_light')}
            </strong>
          </span>
          <button className="btn-ghost btn-sm" onClick={toggleTheme}>
            {theme === 'dark' ? t('utilities.theme_toggle_light') : t('utilities.theme_toggle_dark')}
          </button>
        </div>
      </div>

      {/* Idioma */}
      <div className="card" style={{ marginTop: 24 }}>
        <h2>{t('utilities.language')}</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className={locale === 'es' ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
            onClick={() => setLocale('es')}
          >
            🇪🇸 {t('utilities.lang_es')}
          </button>
          <button
            className={locale === 'en' ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
            onClick={() => setLocale('en')}
          >
            🇬🇧 {t('utilities.lang_en')}
          </button>
        </div>
      </div>

      {/* Backup */}
      <div className="card" style={{ marginTop: 24 }}>
        <h2>{t('utilities.backup')}</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: '0.9rem' }}>
          {t('utilities.backup_desc')}
        </p>

        {backupErr && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{backupErr}</div>}
        {backupMsg && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>{backupMsg}</div>}

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <button className="btn-primary btn-sm" onClick={exportBackup}>
            {t('utilities.backup_export')}
          </button>
          <button
            className="btn-ghost btn-sm"
            disabled={importing}
            onClick={() => fileRef.current?.click()}
          >
            {importing ? t('utilities.backup_importing') : t('utilities.backup_import')}
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

      {/* Importar CSV */}
      <div className="card" style={{ marginTop: 24 }}>
        <h2>{t('utilities.csv_title')}</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 12, fontSize: '0.9rem' }}>
          {t('utilities.csv_desc')}
        </p>

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 16 }}>
          <button className="btn-primary btn-sm" onClick={() => csvFileRef.current?.click()}>
            {t('utilities.csv_select')}
          </button>
          <input
            ref={csvFileRef}
            type="file"
            accept=".csv,text/csv"
            style={{ display: 'none' }}
            onChange={onCsvFile}
          />
          <a
            href="/plantilla-importacion.csv"
            download
            style={{ fontSize: '0.85rem', color: 'var(--accent)', textDecoration: 'underline' }}
          >
            {t('utilities.csv_template')}
          </a>
          <a
            href="/manual-importacion-csv.pdf"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textDecoration: 'underline' }}
          >
            {t('utilities.csv_manual')}
          </a>
        </div>

        {csvParseErr && (
          <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{csvParseErr}</div>
        )}
        {csvErr && (
          <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{csvErr}</div>
        )}
        {csvResult && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ color: 'var(--green)', padding: '6px 0' }}>
              {t('utilities.csv_result')
                .replace('{tx}', csvResult.transactions_added)
                .replace('{div}', csvResult.dividends_added)
                .replace('{sk}', csvResult.skipped)}
            </div>
            {csvResult.errors?.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <span style={{ color: 'var(--red)', fontWeight: 600, fontSize: '0.85rem' }}>
                  {t('utilities.csv_errors')}
                </span>
                <ul style={{ marginTop: 4, paddingLeft: 20, fontSize: '0.82rem', color: 'var(--red)' }}>
                  {csvResult.errors.map((e, i) => (
                    <li key={i}>
                      {t('utilities.csv_error_row')
                        .replace('{row}', e.row)
                        .replace('{ticker}', e.ticker)
                        .replace('{reason}', e.reason)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Preview del CSV parseado */}
        {csvRows && csvRows.length > 0 && (
          <div>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 8 }}>
              {t('utilities.csv_preview')} — {csvRows.length} {csvRows.length === 1 ? 'fila' : 'filas'}
            </p>
            <div className="table-wrap" style={{ maxHeight: 320, overflowY: 'auto', marginBottom: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>{t('utilities.csv_col_row')}</th>
                    <th>{t('utilities.csv_col_type')}</th>
                    <th>{t('utilities.csv_col_ticker')}</th>
                    <th>{t('utilities.csv_col_date')}</th>
                    <th className="num">{t('utilities.csv_col_shares')}</th>
                    <th className="num">{t('utilities.csv_col_price')}</th>
                    <th>{t('utilities.csv_col_currency')}</th>
                  </tr>
                </thead>
                <tbody>
                  {csvRows.map((row, i) => {
                    const hasErr = rowHasError(row)
                    return (
                      <tr key={i} style={hasErr ? { background: 'rgba(229,57,53,0.08)' } : {}}>
                        <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{row._row}</td>
                        <td>
                          <span style={{
                            fontWeight: 600, fontSize: '0.8rem',
                            color: TYPE_COLORS[row.type] ?? 'var(--text-muted)',
                          }}>
                            {row.type || '—'}
                          </span>
                        </td>
                        <td className="ticker">{row.ticker || <span style={{ color: 'var(--red)' }}>!</span>}</td>
                        <td style={{ fontSize: '0.85rem' }}>{row.date || '—'}</td>
                        <td className="num">{row.shares || '—'}</td>
                        <td className="num">
                          {row.type === 'dividend'
                            ? (row.gross_per_share || '—')
                            : (row.price || '—')}
                        </td>
                        <td>{row.currency || 'EUR'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <button
              className="btn-primary btn-sm"
              disabled={csvImporting}
              onClick={importCsv}
            >
              {csvImporting
                ? t('utilities.csv_importing')
                : `${t('utilities.csv_import_btn')} (${csvRows.length})`}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
