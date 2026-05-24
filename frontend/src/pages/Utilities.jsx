import { useRef, useState } from 'react'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'

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
    </div>
  )
}
