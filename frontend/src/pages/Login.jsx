import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useAppConfig } from '../context/AppContext'
import { version } from '../../package.json'
import './Login.css'

export default function Login() {
  const { login } = useAuth()
  const { appName, logoUrl } = useAppConfig()
  const navigate = useNavigate()
  const [form, setForm]   = useState({ username: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy]   = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(form.username, form.password)
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
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

        {error && <div className="state-error" style={{ padding: '8px', marginBottom: 12 }}>{error}</div>}

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
