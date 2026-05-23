import { useRef, useState } from 'react'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'

export default function Utilities() {
  const { theme, toggleTheme } = useAppConfig()

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
      <h1>Utilidades</h1>

      {/* Cambiar contraseña */}
      <div className="card">
        <h2>Cambiar contraseña</h2>
        {pwError && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{pwError}</div>}
        {pwOk    && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>Contraseña actualizada correctamente.</div>}
        <form onSubmit={changePassword}>
          <div className="card-row">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Contraseña actual</label>
              <input
                type="password"
                value={pwForm.current}
                onChange={e => setPwForm(f => ({ ...f, current: e.target.value }))}
                required
              />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Nueva contraseña</label>
              <input
                type="password"
                value={pwForm.newPw}
                onChange={e => setPwForm(f => ({ ...f, newPw: e.target.value }))}
                required
                minLength={8}
              />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Repetir nueva contraseña</label>
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
              {pwBusy ? 'Guardando…' : 'Cambiar contraseña'}
            </button>
          </div>
        </form>
      </div>

      {/* Tema */}
      <div className="card" style={{ marginTop: 24 }}>
        <h2>Apariencia</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Tema actual: <strong style={{ color: 'var(--text)' }}>{theme === 'dark' ? 'Oscuro' : 'Claro'}</strong>
          </span>
          <button className="btn-ghost btn-sm" onClick={toggleTheme}>
            {theme === 'dark' ? '☀ Cambiar a claro' : '◑ Cambiar a oscuro'}
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
