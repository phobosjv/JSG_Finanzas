import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useAppConfig } from '../context/AppContext'
import { api } from '../api/client'
import { version } from '../../package.json'
import './Login.css'

export default function Login() {
  const { login } = useAuth()
  const { appName, logoUrl, t } = useAppConfig()
  const navigate = useNavigate()
  const [form, setForm]           = useState({ username: '', password: '' })
  const [error, setError]         = useState(null)
  const [busy, setBusy]           = useState(false)
  const [isExpired, setIsExpired] = useState(false)
  const [renewalSent, setRenewalSent]   = useState(false)
  const [renewalBusy, setRenewalBusy]   = useState(false)
  const [renewalError, setRenewalError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setIsExpired(false)
    setRenewalSent(false)
    setRenewalError(null)
    try {
      await login(form.username, form.password)
      navigate('/')
    } catch (err) {
      if (err.message === 'account_expired') {
        setIsExpired(true)
      } else {
        setError(err.message)
      }
    } finally {
      setBusy(false)
    }
  }

  async function requestRenewal() {
    setRenewalBusy(true)
    setRenewalError(null)
    try {
      await api.post('/auth/request-renewal', { username: form.username })
      setRenewalSent(true)
    } catch {
      setRenewalError(t('login.renewal_error'))
    } finally {
      setRenewalBusy(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-box card" onSubmit={submit}>
        {logoUrl && (
          <img className="login-logo" src={logoUrl} alt={appName} />
        )}
        <h1 className="login-title">{appName}</h1>
        <p className="login-sub">Seguimiento de cartera de inversión</p>
        <p className="login-version">v{version}</p>

        {error && (
          <div className="state-error" style={{ padding: '8px', marginBottom: 12 }}>
            {error}
          </div>
        )}

        {isExpired && !renewalSent && (
          <div className="state-error" style={{ padding: '8px', marginBottom: 12 }}>
            <p style={{ margin: '0 0 8px' }}>{t('login.error_expired')}</p>
            {renewalError && (
              <p style={{ margin: '0 0 8px', fontSize: '0.85rem' }}>{renewalError}</p>
            )}
            <button
              type="button"
              className="btn-secondary"
              style={{ width: '100%' }}
              onClick={requestRenewal}
              disabled={renewalBusy}
            >
              {renewalBusy ? '…' : t('login.request_renewal')}
            </button>
          </div>
        )}

        {renewalSent && (
          <div className="state-success" style={{ padding: '8px', marginBottom: 12 }}>
            {t('login.renewal_sent')}
          </div>
        )}

        <div className="form-group">
          <label>Usuario</label>
          <input
            type="text"
            value={form.username}
            onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
            autoFocus
            autoComplete="username"
          />
        </div>
        <div className="form-group">
          <label>Contraseña</label>
          <input
            type="password"
            value={form.password}
            onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
            autoComplete="current-password"
          />
        </div>
        <button type="submit" className="btn-primary" style={{ width: '100%' }} disabled={busy}>
          {busy ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
