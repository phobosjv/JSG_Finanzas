import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useAppConfig } from '../context/AppContext'
import SendNotificationModal from '../components/SendNotificationModal'

function fmt(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleDateString('es-ES')
}

function fmtDatetime(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
}

// ---------------------------------------------------------------------------
//  Badge de estado de usuario
// ---------------------------------------------------------------------------

function StatusBadge({ enabled }) {
  return (
    <span className="badge" style={{
      background: enabled ? '#1a3a2a' : '#3a1a1a',
      color: enabled ? 'var(--green)' : 'var(--red)',
    }}>
      {enabled ? 'Activo' : 'Inactivo'}
    </span>
  )
}

// ---------------------------------------------------------------------------
//  Modal: habilitar / deshabilitar usuario
// ---------------------------------------------------------------------------

function UserStatusModal({ user, onClose, onDone }) {
  const enabling = !user.is_enabled
  const [annotation, setAnnotation] = useState('')
  const [withExpiry, setWithExpiry] = useState(false)
  const [expiryDate, setExpiryDate] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api.patch(`/admin/users/${user.id}/status`, {
        enabled: enabling,
        annotation: annotation || null,
      })
      // Si se está habilitando y se ha marcado poner fecha de caducidad
      if (enabling && withExpiry && expiryDate) {
        await api.patch(`/admin/users/${user.id}/expiry`, { expires_at: expiryDate })
      }
      onDone()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>{enabling ? 'Habilitar' : 'Deshabilitar'} — {user.username}</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Anotación (opcional)</label>
            <input
              type="text"
              value={annotation}
              onChange={e => setAnnotation(e.target.value)}
              autoFocus
              placeholder={enabling ? 'Motivo de reactivación…' : 'Motivo de suspensión…'}
            />
          </div>
          {enabling && (
            <div className="form-group">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <input
                  type="checkbox"
                  id="with_expiry"
                  checked={withExpiry}
                  onChange={e => setWithExpiry(e.target.checked)}
                  style={{ width: 'auto', margin: 0 }}
                />
                <label htmlFor="with_expiry" style={{ margin: 0 }}>Poner fecha de caducidad</label>
              </div>
              {withExpiry && (
                <input
                  type="date"
                  value={expiryDate}
                  onChange={e => setExpiryDate(e.target.value)}
                  min={new Date().toISOString().slice(0, 10)}
                  required={withExpiry}
                />
              )}
            </div>
          )}
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
            <button
              type="submit"
              className={enabling ? 'btn-primary' : 'btn-danger'}
              disabled={busy}
            >
              {busy ? 'Guardando…' : (enabling ? 'Habilitar' : 'Deshabilitar')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
//  Modal: fecha de caducidad
// ---------------------------------------------------------------------------

function ExpiryModal({ user, onClose, onDone }) {
  const [expiryDate, setExpiryDate] = useState(
    user.expires_at ? user.expires_at.slice(0, 10) : ''
  )
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api.patch(`/admin/users/${user.id}/expiry`, {
        expires_at: expiryDate || null,
      })
      onDone()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>Caducidad — {user.username}</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Fecha de caducidad (dejar vacío para sin límite)</label>
            <input
              type="date"
              value={expiryDate}
              onChange={e => setExpiryDate(e.target.value)}
              autoFocus
            />
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

// ---------------------------------------------------------------------------
//  Modal: historial de estados
// ---------------------------------------------------------------------------

const STATUS_LABELS = {
  registered: { label: 'Alta',         color: 'var(--accent)' },
  enabled:    { label: 'Habilitado',   color: 'var(--green)' },
  disabled:   { label: 'Deshabilitado', color: 'var(--red)' },
  expired:    { label: 'Caducado',     color: 'var(--yellow)' },
}

function UserHistoryModal({ user, onClose }) {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/admin/users/${user.id}/history`)
      .then(setHistory)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [user.id])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <h2>Historial — {user.username}</h2>
        {loading ? (
          <div className="state-loading"><div className="spinner" /></div>
        ) : history.length === 0 ? (
          <div className="state-empty">Sin historial registrado.</div>
        ) : (
          <div style={{ maxHeight: 360, overflowY: 'auto' }}>
            {history.map(entry => {
              const meta = STATUS_LABELS[entry.status] ?? { label: entry.status, color: 'var(--text-muted)' }
              return (
                <div key={entry.id} style={{
                  display: 'flex', gap: 12, padding: '10px 0',
                  borderBottom: '1px solid var(--border)',
                }}>
                  <div style={{
                    width: 10, height: 10, borderRadius: '50%',
                    background: meta.color, flexShrink: 0, marginTop: 4,
                  }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ fontWeight: 600, color: meta.color }}>{meta.label}</span>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                        {fmtDatetime(entry.created_at)}
                      </span>
                    </div>
                    {entry.actor_username && (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        por {entry.actor_username}
                      </div>
                    )}
                    {entry.annotation && (
                      <div style={{ fontSize: '0.85rem', marginTop: 2 }}>{entry.annotation}</div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
        <div className="modal-actions">
          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
//  Modal: cambiar contraseña de usuario
// ---------------------------------------------------------------------------

function ChangePasswordModal({ user, onClose, onDone }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (password.length < 8) { setError('Mínimo 8 caracteres'); return }
    setBusy(true); setError(null)
    try {
      await api.patch(`/admin/users/${user.id}/password`, { password })
      onDone()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>Cambiar contraseña — {user.username}</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Nueva contraseña</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoFocus
              required
              minLength={8}
            />
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

// ---------------------------------------------------------------------------
//  Modal: crear usuario
// ---------------------------------------------------------------------------

function CreateUserModal({ onClose, onCreated }) {
  const { t } = useAppConfig()
  const [form, setForm] = useState({ username: '', password: '', is_admin: false, email: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  function field(name) {
    return {
      value: form[name],
      onChange: e => setForm(f => ({ ...f, [name]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })),
    }
  }

  async function submit(e) {
    e.preventDefault()
    if (form.username.trim().length < 3) { setError('Usuario: mínimo 3 caracteres'); return }
    if (form.password.length < 8) { setError('Contraseña: mínimo 8 caracteres'); return }
    setBusy(true); setError(null)
    try {
      await api.post('/admin/users', {
        username: form.username.trim(),
        password: form.password,
        is_admin: form.is_admin,
        email: form.email.trim() || null,
      })
      onCreated()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>Nuevo usuario</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>Nombre de usuario</label>
            <input type="text" autoFocus {...field('username')} required minLength={3} />
          </div>
          <div className="form-group">
            <label>Contraseña</label>
            <input type="password" {...field('password')} required minLength={8} />
          </div>
          <div className="form-group">
            <label>{t('admin.email_user_label')}</label>
            <input
              type="email"
              {...field('email')}
              placeholder={t('admin.email_user_placeholder')}
            />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
              ℹ️ {t('admin.email_admin_only_note')}
            </span>
          </div>
          <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              id="is_admin"
              checked={form.is_admin}
              onChange={e => setForm(f => ({ ...f, is_admin: e.target.checked }))}
              style={{ width: 'auto', margin: 0 }}
            />
            <label htmlFor="is_admin" style={{ margin: 0 }}>Administrador</label>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Creando…' : 'Crear'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Modal: editar email de un usuario
// ---------------------------------------------------------------------------

function EditEmailModal({ user, onClose, onDone }) {
  const { t } = useAppConfig()
  const [email, setEmail] = useState(user.email || '')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api.patch(`/admin/users/${user.id}/email`, { email: email.trim() || null })
      onDone()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 420 }}>
        <h2>{t('admin.email_edit_title')} — {user.username}</h2>
        {error && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={submit}>
          <div className="form-group">
            <label>{t('admin.email_user_label')}</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder={t('admin.email_user_placeholder')}
              autoFocus
            />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
              ℹ️ {t('admin.email_admin_only_note')}
            </span>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Guardando…' : t('admin.email_user_save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
//  Modal: splits / contrasplits de un valor
// ---------------------------------------------------------------------------

function SplitsModal({ security, onClose }) {
  const [splits, setSplits]   = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm]       = useState({ ex_date: '', ratio_num: 2, ratio_den: 1, notes: '' })
  const [busy, setBusy]       = useState(false)
  const [err, setErr]         = useState(null)

  async function load() {
    setLoading(true)
    try { setSplits(await api.get(`/admin/securities/${security.id}/splits`)) }
    catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [security.id])

  async function submit(e) {
    e.preventDefault()
    if (!form.ex_date) { setErr('La fecha es obligatoria'); return }
    if (Number(form.ratio_num) < 1 || Number(form.ratio_den) < 1) {
      setErr('Los ratios deben ser >= 1'); return
    }
    setBusy(true); setErr(null)
    try {
      await api.post(`/admin/securities/${security.id}/splits`, {
        ex_date: form.ex_date,
        ratio_num: Number(form.ratio_num),
        ratio_den: Number(form.ratio_den),
        notes: form.notes || null,
      })
      setForm({ ex_date: '', ratio_num: 2, ratio_den: 1, notes: '' })
      await load()
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function del(id) {
    if (!confirm('¿Eliminar este split?')) return
    setErr(null)
    try { await api.delete(`/admin/splits/${id}`); await load() }
    catch (e) { setErr(e.message) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 560 }} onClick={e => e.stopPropagation()}>
        <h2>Splits — {security.yahoo_ticker}</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: 16 }}>
          Los splits normalizan automáticamente las transacciones anteriores a la fecha efectiva
          para todos los usuarios que posean este valor.
        </p>

        {err && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{err}</div>}

        {/* Formulario de nuevo split */}
        <form onSubmit={submit} style={{ marginBottom: 20 }}>
          <div className="card-row" style={{ alignItems: 'flex-end', gap: 8 }}>
            <div className="form-group" style={{ flex: '0 0 130px', marginBottom: 0 }}>
              <label>Fecha efectiva</label>
              <input
                type="date"
                value={form.ex_date}
                onChange={e => setForm(f => ({ ...f, ex_date: e.target.value }))}
                required
              />
            </div>
            <div className="form-group" style={{ flex: '0 0 70px', marginBottom: 0 }}>
              <label>Nuevas</label>
              <input
                type="number" min={1} style={{ width: '100%' }}
                value={form.ratio_num}
                onChange={e => setForm(f => ({ ...f, ratio_num: e.target.value }))}
                required
              />
            </div>
            <span style={{ alignSelf: 'center', color: 'var(--text-muted)', fontSize: '1.2rem', paddingBottom: 4 }}>:</span>
            <div className="form-group" style={{ flex: '0 0 70px', marginBottom: 0 }}>
              <label>Antiguas</label>
              <input
                type="number" min={1} style={{ width: '100%' }}
                value={form.ratio_den}
                onChange={e => setForm(f => ({ ...f, ratio_den: e.target.value }))}
                required
              />
            </div>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label>Notas</label>
              <input
                type="text"
                value={form.notes}
                onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Opcional"
              />
            </div>
            <button type="submit" className="btn-primary btn-sm" disabled={busy} style={{ marginBottom: 0 }}>
              {busy ? '…' : '+ Añadir'}
            </button>
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 4 }}>
            Ejemplo: split 2:1 → Nuevas=2, Antiguas=1 · Contrasplit 1:2 → Nuevas=1, Antiguas=2
          </div>
        </form>

        {/* Lista de splits */}
        {loading ? (
          <div className="state-loading"><div className="spinner" /></div>
        ) : splits.length === 0 ? (
          <div className="state-empty">No hay splits registrados para este valor.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fecha efectiva</th>
                  <th>Ratio</th>
                  <th>Notas</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {splits.map(s => (
                  <tr key={s.id}>
                    <td>{s.ex_date}</td>
                    <td className="num">
                      <strong>{s.ratio_num}</strong>:{s.ratio_den}
                      <span style={{ marginLeft: 6, color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                        ({s.ratio_num > s.ratio_den ? 'split' : 'contrasplit'})
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{s.notes ?? '—'}</td>
                    <td>
                      <button className="btn-danger btn-sm" onClick={() => del(s.id)}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="modal-actions" style={{ marginTop: 16 }}>
          <button className="btn-ghost" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Subsección: Tramos IRPF
// ---------------------------------------------------------------------------

function TaxBracketsSubsection() {
  const { t } = useAppConfig()
  const [brackets, setBrackets] = useState([])
  const [editing, setEditing]   = useState(null)  // null | {id?, min_amount, max_amount, rate, sort_order}
  const [busy, setBusy]         = useState(false)
  const [err, setErr]           = useState(null)
  const [msg, setMsg]           = useState(null)

  function load() {
    api.get('/admin/config/tax-brackets').then(setBrackets).catch(() => {})
  }

  useEffect(() => { load() }, [])

  function startAdd() {
    const nextOrder = brackets.length > 0 ? Math.max(...brackets.map(b => b.sort_order)) + 1 : 0
    setEditing({ min_amount: '', max_amount: '', rate: '', sort_order: nextOrder })
    setErr(null); setMsg(null)
  }

  function startEdit(b) {
    setEditing({ ...b, max_amount: b.max_amount ?? '' })
    setErr(null); setMsg(null)
  }

  async function saveEditing(e) {
    e.preventDefault()
    setBusy(true); setErr(null); setMsg(null)
    try {
      const payload = {
        min_amount: Number(editing.min_amount),
        max_amount: editing.max_amount === '' || editing.max_amount === null ? null : Number(editing.max_amount),
        rate: Number(editing.rate),
        sort_order: Number(editing.sort_order),
      }
      if (editing.id) {
        await api.put(`/admin/config/tax-brackets/${editing.id}`, payload)
      } else {
        await api.post('/admin/config/tax-brackets', payload)
      }
      setMsg(t('admin.bracket_saved'))
      setEditing(null)
      load()
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function deleteBracket(id) {
    if (!window.confirm(t('admin.bracket_confirm_delete'))) return
    try {
      await api.delete(`/admin/config/tax-brackets/${id}`)
      load()
    } catch (e) { setErr(e.message) }
  }

  return (
    <div style={{ marginTop: 28 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: '1rem' }}>{t('admin.tax_brackets')}</h3>
        <button className="btn-ghost btn-sm" onClick={startAdd}>{t('admin.bracket_add')}</button>
      </div>

      {err && <div className="state-error" style={{ padding: 6, marginBottom: 8 }}>{err}</div>}
      {msg && <div style={{ color: 'var(--green)', padding: 6, marginBottom: 8 }}>{msg}</div>}

      <table className="table" style={{ marginBottom: 0 }}>
        <thead>
          <tr>
            <th>{t('admin.bracket_from')}</th>
            <th>{t('admin.bracket_to')}</th>
            <th>{t('admin.bracket_rate')}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {brackets.map(b => (
            <tr key={b.id}>
              <td>{Number(b.min_amount).toLocaleString('es-ES')} €</td>
              <td>{b.max_amount !== null && b.max_amount !== undefined ? `${Number(b.max_amount).toLocaleString('es-ES')} €` : t('admin.bracket_unlimited')}</td>
              <td>{Number(b.rate)} %</td>
              <td style={{ display: 'flex', gap: 6 }}>
                <button className="btn-ghost btn-sm" onClick={() => startEdit(b)}>{t('admin.bracket_edit')}</button>
                <button className="btn-ghost btn-sm" style={{ color: 'var(--red, #e53935)' }} onClick={() => deleteBracket(b.id)}>{t('admin.bracket_delete')}</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {editing !== null && (
        <form onSubmit={saveEditing} style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 12, padding: 12, background: 'var(--bg-alt, var(--bg-card))', borderRadius: 6 }}>
          <div className="form-group" style={{ flex: '0 0 auto', marginBottom: 0 }}>
            <label>{t('admin.bracket_from')}</label>
            <input type="number" min="0" step="any" style={{ width: 100 }}
              value={editing.min_amount}
              onChange={e => setEditing(v => ({ ...v, min_amount: e.target.value }))} required />
          </div>
          <div className="form-group" style={{ flex: '0 0 auto', marginBottom: 0 }}>
            <label>{t('admin.bracket_to')} ({t('admin.bracket_no_limit')})</label>
            <input type="number" min="0" step="any" style={{ width: 100 }}
              value={editing.max_amount}
              placeholder="∞"
              onChange={e => setEditing(v => ({ ...v, max_amount: e.target.value }))} />
          </div>
          <div className="form-group" style={{ flex: '0 0 auto', marginBottom: 0 }}>
            <label>{t('admin.bracket_rate')}</label>
            <input type="number" min="0.01" max="99.99" step="0.01" style={{ width: 80 }}
              value={editing.rate}
              onChange={e => setEditing(v => ({ ...v, rate: e.target.value }))} required />
          </div>
          <div className="form-group" style={{ flex: '0 0 auto', marginBottom: 0 }}>
            <label>Orden</label>
            <input type="number" min="0" step="1" style={{ width: 70 }}
              value={editing.sort_order}
              onChange={e => setEditing(v => ({ ...v, sort_order: e.target.value }))} required />
          </div>
          <button type="submit" className="btn-primary btn-sm" disabled={busy}>{busy ? '…' : t('common.save')}</button>
          <button type="button" className="btn-ghost btn-sm" onClick={() => setEditing(null)}>{t('common.cancel')}</button>
        </form>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Configuración del sistema
// ---------------------------------------------------------------------------

function ConfigSection() {
  const { setAppName, logoUrl, refreshLogo, currencies: ctxCurrencies, t } = useAppConfig()
  const [interval, setInterval]     = useState(null)
  const [inputVal, setInputVal]     = useState(5)
  const [appNameVal, setAppNameVal] = useState('')
  const [busy, setBusy]             = useState(false)
  const [nameBusy, setNameBusy]     = useState(false)
  const [refreshBusy, setRefreshBusy] = useState(false)
  const [logoBusy, setLogoBusy]     = useState(false)
  const logoFileRef                 = useRef(null)
  const [currencyList, setCurrencyList] = useState(ctxCurrencies.filter(c => c !== 'EUR'))
  const [newCurrency, setNewCurrency]   = useState('')
  const [currencyBusy, setCurrencyBusy] = useState(false)
  const [dustVal, setDustVal]       = useState('0.10')
  const [dustBusy, setDustBusy]     = useState(false)
  const [msg, setMsg]               = useState(null)
  const [err, setErr]               = useState(null)

  const LOGO_MAX_BYTES = 1024 * 1024
  const LOGO_ACCEPT = 'image/png,image/jpeg,image/webp,image/svg+xml'

  async function onLogoFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setMsg(null); setErr(null)
    if (!file.type || !LOGO_ACCEPT.split(',').includes(file.type)) {
      setErr(t('admin.logo_bad_type')); e.target.value = ''; return
    }
    if (file.size > LOGO_MAX_BYTES) {
      setErr(t('admin.logo_too_big')); e.target.value = ''; return
    }
    setLogoBusy(true)
    try {
      const dataUrl = await new Promise((resolve, reject) => {
        const r = new FileReader()
        r.onload = () => resolve(r.result)
        r.onerror = () => reject(new Error('read error'))
        r.readAsDataURL(file)
      })
      await api.put('/admin/config/logo', { data: dataUrl, mime: file.type })
      await refreshLogo()
      setMsg(t('admin.logo_saved'))
    } catch (e2) { setErr(e2.message) }
    finally { setLogoBusy(false); e.target.value = '' }
  }

  async function removeLogo() {
    if (!window.confirm(t('admin.logo_confirm_remove'))) return
    setMsg(null); setErr(null); setLogoBusy(true)
    try {
      await api.delete('/admin/config/logo')
      await refreshLogo()
      setMsg(t('admin.logo_removed'))
    } catch (e2) { setErr(e2.message) }
    finally { setLogoBusy(false) }
  }

  function addCurrency() {
    const code = newCurrency.trim().toUpperCase()
    if (code.length !== 3 || !/^[A-Z]{3}$/.test(code)) return
    if (code === 'EUR' || currencyList.includes(code)) return
    setCurrencyList(prev => [...prev, code])
    setNewCurrency('')
  }

  function removeCurrency(code) {
    setCurrencyList(prev => prev.filter(c => c !== code))
  }

  async function saveCurrencies() {
    setCurrencyBusy(true); setMsg(null); setErr(null)
    try {
      await api.patch('/admin/config/currencies', { currencies: currencyList })
      // Recargar config para que AppContext actualice el contexto global
      const d = await api.get('/config')
      if (Array.isArray(d?.supported_currencies)) {
        setCurrencyList(d.supported_currencies.filter(c => c !== 'EUR'))
      }
      setMsg(t('admin.currencies_saved'))
    } catch (e2) { setErr(e2.message) }
    finally { setCurrencyBusy(false) }
  }

  useEffect(() => {
    api.get('/admin/config').then(d => {
      setInterval(d.snapshot_interval_minutes)
      setInputVal(d.snapshot_interval_minutes)
      setAppNameVal(d.app_name ?? 'JSG Soft.')
      if (d.dust_threshold != null) setDustVal(String(d.dust_threshold))
    }).catch(() => {})
  }, [])

  async function saveDust(e) {
    e.preventDefault()
    setDustBusy(true); setMsg(null); setErr(null)
    try {
      const d = await api.patch('/admin/config/dust-threshold', { dust_threshold: dustVal })
      setDustVal(String(d.dust_threshold))
      setMsg(t('admin.dust_saved'))
    } catch (e) { setErr(e.message) }
    finally { setDustBusy(false) }
  }

  async function saveInterval(e) {
    e.preventDefault()
    setBusy(true); setMsg(null); setErr(null)
    try {
      const d = await api.patch('/admin/config/snapshot-interval', { minutes: Number(inputVal) })
      setInterval(d.snapshot_interval_minutes)
      setMsg('Intervalo actualizado')
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function saveAppName(e) {
    e.preventDefault()
    setNameBusy(true); setMsg(null); setErr(null)
    try {
      const d = await api.patch('/admin/config/app-name', { app_name: appNameVal })
      setAppName(d.app_name)
      setMsg('Nombre de la aplicación actualizado')
    } catch (e) { setErr(e.message) }
    finally { setNameBusy(false) }
  }

  async function refreshAll() {
    setRefreshBusy(true); setMsg(null); setErr(null)
    try {
      const d = await api.post('/markets/refresh-all')
      setMsg(d.detail)
    } catch (e) { setErr(e.message) }
    finally { setRefreshBusy(false) }
  }

  return (
    <div className="card" style={{ marginTop: 24 }}>
      <h2>Configuración del sistema</h2>
      {err && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{err}</div>}
      {msg && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>{msg}</div>}

      {/* Nombre de la aplicación */}
      <form onSubmit={saveAppName} style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 20 }}>
        <div className="form-group" style={{ flex: '1 1 200px', marginBottom: 0 }}>
          <label>Nombre de la aplicación</label>
          <input
            type="text"
            value={appNameVal}
            onChange={e => setAppNameVal(e.target.value)}
            maxLength={100}
            placeholder="JSG Soft."
          />
        </div>
        <button type="submit" className="btn-primary btn-sm" disabled={nameBusy || !appNameVal.trim()}>
          {nameBusy ? 'Guardando…' : 'Aplicar nombre'}
        </button>
      </form>

      {/* Divisas soportadas */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ display: 'block', marginBottom: 4 }}>{t('admin.currencies')}</label>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 0, marginBottom: 10 }}>
          {t('admin.currencies_note')}
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <span style={{
            padding: '2px 10px', borderRadius: 4, fontSize: '0.85rem',
            background: 'var(--bg-input)', color: 'var(--text-muted)',
            border: '1px solid var(--border)',
          }}>EUR</span>
          {currencyList.map(c => (
            <span key={c} style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '2px 8px', borderRadius: 4, fontSize: '0.85rem',
              background: 'var(--accent-dim)', color: 'var(--accent)',
              border: '1px solid var(--accent)',
            }}>
              {c}
              <button
                type="button"
                onClick={() => removeCurrency(c)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', padding: 0, fontSize: '0.8rem' }}
              >×</button>
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="text"
            value={newCurrency}
            onChange={e => setNewCurrency(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addCurrency())}
            maxLength={3}
            placeholder={t('admin.currencies_placeholder')}
            style={{ width: 80, textTransform: 'uppercase' }}
          />
          <button type="button" className="btn-ghost btn-sm" onClick={addCurrency}>
            + {t('admin.currencies_add')}
          </button>
          <button type="button" className="btn-primary btn-sm" disabled={currencyBusy} onClick={saveCurrencies}>
            {currencyBusy ? '…' : t('common.save')}
          </button>
        </div>
      </div>

      {/* Logotipo de la aplicación */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ display: 'block', marginBottom: 6 }}>{t('admin.logo')}</label>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 0, marginBottom: 10 }}>
          {t('admin.logo_help')}
        </p>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{
            width: 96, height: 96, borderRadius: 8, border: '1px solid var(--border)',
            background: 'var(--bg-input)', display: 'flex', alignItems: 'center',
            justifyContent: 'center', overflow: 'hidden', flexShrink: 0,
          }}>
            {logoUrl
              ? <img src={logoUrl} alt={t('admin.logo_current')} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
              : <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textAlign: 'center', padding: 6 }}>{t('admin.logo_none')}</span>
            }
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <input
              ref={logoFileRef}
              type="file"
              accept={LOGO_ACCEPT}
              onChange={onLogoFile}
              style={{ display: 'none' }}
            />
            <button
              type="button"
              className="btn-primary btn-sm"
              disabled={logoBusy}
              onClick={() => logoFileRef.current?.click()}
            >
              {logoBusy ? '…' : t('admin.logo_upload')}
            </button>
            {logoUrl && (
              <button type="button" className="btn-ghost btn-sm" disabled={logoBusy} onClick={removeLogo}>
                {t('admin.logo_remove')}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Intervalo de snapshots */}
      <form onSubmit={saveInterval} style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 16 }}>
        <div className="form-group" style={{ flex: '0 0 auto', marginBottom: 0 }}>
          <label>Intervalo actualización precios (min)</label>
          <input
            type="number" min={5} max={60}
            value={inputVal}
            onChange={e => setInputVal(e.target.value)}
            style={{ width: 80 }}
          />
        </div>
        <button type="submit" className="btn-primary btn-sm" disabled={busy || interval === null}>
          {busy ? 'Guardando…' : 'Guardar'}
        </button>
        {interval !== null && (
          <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', alignSelf: 'center' }}>
            Actual: {interval} min
          </span>
        )}
      </form>

      <button className="btn-ghost btn-sm" disabled={refreshBusy} onClick={refreshAll}>
        {refreshBusy ? 'Actualizando…' : '↺ Actualizar todos los valores ahora'}
      </button>

      {/* Umbral de "polvo" (posiciones residuales por redondeo) */}
      <form onSubmit={saveDust} style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 20, marginBottom: 4 }}>
        <div className="form-group" style={{ flex: '0 0 auto', marginBottom: 0 }}>
          <label>{t('admin.dust_label')}</label>
          <input
            type="number" min={0} step="0.01"
            value={dustVal}
            onChange={e => setDustVal(e.target.value)}
            style={{ width: 90 }}
          />
        </div>
        <button type="submit" className="btn-primary btn-sm" disabled={dustBusy}>
          {dustBusy ? t('admin.saving') : t('admin.save')}
        </button>
      </form>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: 0, maxWidth: 560 }}>
        {t('admin.dust_help')}
      </p>

      {/* ── Tramos IRPF ─────────────────────────────── */}
      <hr style={{ margin: '24px 0', borderColor: 'var(--border-color, #333)' }} />
      <TaxBracketsSubsection />
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Configuración de correo electrónico
// ---------------------------------------------------------------------------

const EMAIL_PROVIDERS = [
  { key: 'smtp_gmail',   label: 'Gmail',           icon: '📧' },
  { key: 'smtp_outlook', label: 'Outlook / Microsoft 365', icon: '📨' },
  { key: 'smtp_generic', label: 'SMTP genérico',   icon: '⚙️' },
  { key: 'sendgrid',     label: 'SendGrid',        icon: '📤' },
  { key: 'mailgun',      label: 'Mailgun',         icon: '📬' },
]

const SMTP_PRESETS = {
  smtp_gmail:   { host: 'smtp.gmail.com',     port: 587 },
  smtp_outlook: { host: 'smtp.office365.com', port: 587 },
}

function EmailConfigSection() {
  const { t } = useAppConfig()
  const [cfg, setCfg] = useState({
    provider: 'smtp_gmail',
    from_name: '',
    from_address: '',
    smtp_host: '',
    smtp_port: 587,
    smtp_user: '',
    smtp_password: '',
    smtp_use_tls: true,
    api_key: '',
    mailgun_domain: '',
  })
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.get('/admin/config/email')
      .then(data => {
        setCfg(prev => ({
          ...prev,
          ...data,
          smtp_password: data.smtp_password || '',
          api_key: data.api_key || '',
        }))
        setLoaded(true)
      })
      .catch(() => setLoaded(true))
  }, [])

  function updateField(name, value) {
    setCfg(prev => ({ ...prev, [name]: value }))
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true); setMsg(null); setErr(null)
    try {
      const payload = { ...cfg }
      // Si la contraseña/api_key está vacía, no la enviamos
      if (!payload.smtp_password) delete payload.smtp_password
      if (!payload.api_key) delete payload.api_key
      await api.patch('/admin/config/email', payload)
      setMsg(t('admin.email_saved_ok'))
      // Después de guardar, recargar para reflejar máscaras
      const fresh = await api.get('/admin/config/email')
      setCfg(prev => ({
        ...prev,
        ...fresh,
        smtp_password: fresh.smtp_password || '',
        api_key: fresh.api_key || '',
      }))
    } catch (ex) { setErr(ex.message) }
    finally { setSaving(false) }
  }

  async function testEmail() {
    setTesting(true); setMsg(null); setErr(null)
    try {
      const data = await api.post('/admin/config/email/test', {})
      setMsg(t('admin.email_test_ok').replace('{email}', data.sent_to))
    } catch (ex) { setErr(ex.message) }
    finally { setTesting(false) }
  }

  const isSmtp = cfg.provider.startsWith('smtp_')
  const hasPreset = cfg.provider in SMTP_PRESETS

  return (
    <div className="card" style={{ marginTop: 0 }}>
      <h2>{t('admin.email_section_title')}</h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: '0.9rem' }}>
        {t('admin.email_section_desc')}
      </p>

      {msg && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12, fontSize: '0.85rem' }}>{msg}</div>}
      {err && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{err}</div>}

      <form onSubmit={save}>
        {/* Selector de proveedor */}
        <div className="form-group">
          <label>{t('admin.email_provider_label')}</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {EMAIL_PROVIDERS.map(p => (
              <button
                key={p.key}
                type="button"
                className={cfg.provider === p.key ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
                onClick={() => updateField('provider', p.key)}
                style={{ display: 'flex', alignItems: 'center', gap: 4 }}
              >
                {p.icon} {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Texto de ayuda por proveedor */}
        {cfg.provider !== 'smtp_generic' && (
          <div style={{
            background: 'var(--bg-input)',
            borderRadius: 6,
            padding: '10px 14px',
            marginBottom: 16,
            fontSize: '0.82rem',
            color: 'var(--text-muted)',
            lineHeight: 1.5,
          }}>
            {t(`admin.email_help_${cfg.provider}`)}
          </div>
        )}

        {/* Campos comunes */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="form-group">
            <label>{t('admin.email_from_name')}</label>
            <input
              type="text"
              value={cfg.from_name}
              onChange={e => updateField('from_name', e.target.value)}
              placeholder="JSG Portfolio"
              required
            />
          </div>
          <div className="form-group">
            <label>{t('admin.email_from_address')}</label>
            <input
              type="email"
              value={cfg.from_address}
              onChange={e => updateField('from_address', e.target.value)}
              placeholder="noreply@tudominio.com"
              required
            />
          </div>
        </div>

        {/* Campos SMTP */}
        {isSmtp && (
          <>
            {!hasPreset && (
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
                <div className="form-group">
                  <label>{t('admin.email_smtp_host')}</label>
                  <input
                    type="text"
                    value={cfg.smtp_host}
                    onChange={e => updateField('smtp_host', e.target.value)}
                    placeholder="smtp.tuservidor.com"
                  />
                </div>
                <div className="form-group">
                  <label>{t('admin.email_smtp_port')}</label>
                  <input
                    type="number"
                    value={cfg.smtp_port}
                    onChange={e => updateField('smtp_port', parseInt(e.target.value) || 587)}
                    min={1}
                    max={65535}
                  />
                </div>
              </div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div className="form-group">
                <label>{t('admin.email_smtp_user')}</label>
                <input
                  type="text"
                  value={cfg.smtp_user}
                  onChange={e => updateField('smtp_user', e.target.value)}
                  placeholder={cfg.provider === 'smtp_gmail' ? 'tucuenta@gmail.com' : 'usuario'}
                  autoComplete="username"
                />
              </div>
              <div className="form-group">
                <label>{t('admin.email_smtp_password')}</label>
                <input
                  type="password"
                  value={cfg.smtp_password}
                  onChange={e => updateField('smtp_password', e.target.value)}
                  placeholder={cfg.smtp_password === '***' ? '••••••••••••••••' : ''}
                  autoComplete="new-password"
                />
              </div>
            </div>
            {!hasPreset && (
              <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  id="smtp_tls"
                  checked={cfg.smtp_use_tls}
                  onChange={e => updateField('smtp_use_tls', e.target.checked)}
                  style={{ width: 'auto', margin: 0 }}
                />
                <label htmlFor="smtp_tls" style={{ margin: 0 }}>{t('admin.email_smtp_tls')}</label>
              </div>
            )}
          </>
        )}

        {/* SendGrid */}
        {cfg.provider === 'sendgrid' && (
          <div className="form-group">
            <label>{t('admin.email_api_key')}</label>
            <input
              type="password"
              value={cfg.api_key}
              onChange={e => updateField('api_key', e.target.value)}
              placeholder={cfg.api_key === '***' ? '••••••••••••••••' : 'SG.XXXX…'}
              autoComplete="new-password"
            />
          </div>
        )}

        {/* Mailgun */}
        {cfg.provider === 'mailgun' && (
          <>
            <div className="form-group">
              <label>{t('admin.email_api_key')}</label>
              <input
                type="password"
                value={cfg.api_key}
                onChange={e => updateField('api_key', e.target.value)}
                placeholder={cfg.api_key === '***' ? '••••••••••••••••' : 'key-XXXX…'}
                autoComplete="new-password"
              />
            </div>
            <div className="form-group">
              <label>{t('admin.email_mailgun_domain')}</label>
              <input
                type="text"
                value={cfg.mailgun_domain}
                onChange={e => updateField('mailgun_domain', e.target.value)}
                placeholder="mg.tudominio.com"
              />
            </div>
          </>
        )}

        <div style={{ display: 'flex', gap: 12, marginTop: 8, flexWrap: 'wrap' }}>
          <button type="submit" className="btn-primary btn-sm" disabled={saving}>
            {saving ? t('admin.email_saving') : t('admin.email_save')}
          </button>
          <button
            type="button"
            className="btn-ghost btn-sm"
            disabled={testing}
            onClick={testEmail}
          >
            {testing ? t('admin.email_testing') : t('admin.email_test')}
          </button>
        </div>
      </form>
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Actualización forzada del historial de precios
// ---------------------------------------------------------------------------

function ForceHistoryUpdateSection() {
  const [jobStatus, setJobStatus] = useState(null)   // objeto { running, started_at, finished_at, result }
  const [confirming, setConfirming] = useState(false)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  // Rellenado de ISINs vacíos desde Yahoo (job en segundo plano + polling)
  const [isinRunning, setIsinRunning] = useState(false)
  const [isinStatus, setIsinStatus] = useState(null)  // { running, total, checked, updated, not_found, result, finished_at }

  async function fillIsins() {
    setErr(null)
    try {
      await api.post('/admin/securities/fill-isins')
      setIsinRunning(true)
      try { setIsinStatus(await api.get('/admin/securities/fill-isins/status')) } catch { /* el polling lo recogerá */ }
    } catch (e) { setErr(e.message) }
  }

  // Polling del estado del rellenado de ISINs mientras esté en curso
  useEffect(() => {
    if (!isinRunning) return
    const id = setInterval(async () => {
      try {
        const s = await api.get('/admin/securities/fill-isins/status')
        setIsinStatus(s)
        if (!s.running) { clearInterval(id); setIsinRunning(false) }
      } catch { /* red caída: reintenta al siguiente tick */ }
    }, 2000)
    return () => clearInterval(id)
  }, [isinRunning])

  // Carga el estado inicial al montar (por si hay un job en curso tras F5)
  useEffect(() => {
    api.get('/admin/force-history-update/status').then(setJobStatus).catch(() => {})
    api.get('/admin/securities/fill-isins/status').then(s => {
      if (s?.running) setIsinRunning(true)
      else if (s?.finished_at) setIsinStatus(s)
    }).catch(() => {})
  }, [])

  // Polling automático mientras running === true
  useEffect(() => {
    if (!jobStatus?.running) return
    const id = setInterval(async () => {
      try {
        const s = await api.get('/admin/force-history-update/status')
        setJobStatus(s)
        if (!s.running) {
          clearInterval(id)
          if (s.result === 'ok') setMsg('Historial actualizado correctamente. Los precios del gráfico son ahora exactos.')
          else setErr(s.result ?? 'Error desconocido')
        }
      } catch { /* red caída: reintentamos en el siguiente tick */ }
    }, 3000)
    return () => clearInterval(id)
  }, [jobStatus?.running])

  async function start() {
    setConfirming(false)
    setMsg(null); setErr(null)
    try {
      await api.post('/admin/force-history-update')
      // Refresca el estado para que el polling vea running=true
      const s = await api.get('/admin/force-history-update/status')
      setJobStatus(s)
    } catch (e) { setErr(e.message) }
  }

  const running = jobStatus?.running ?? false

  return (
    <div className="card" style={{ marginTop: 24 }}>
      <h2>Actualización manual del historial</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: 12 }}>
        Descarga los últimos 7 días de historial de precios para todos los valores y
        sobrescribe cualquier precio incorrecto almacenado (p.&nbsp;ej. tras un ex-date de dividendo).
        Al terminar también actualiza los snapshots de precios en vivo.
      </p>

      {err && (
        <div className="state-error" style={{ padding: 8, marginBottom: 12, cursor: 'pointer' }} onClick={() => setErr(null)}>
          {err} <span style={{ float: 'right' }}>✕</span>
        </div>
      )}
      {msg && (
        <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>{msg}</div>
      )}

      {running ? (
        /* Estado: en curso */
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          <div className="spinner" style={{ width: 18, height: 18, flexShrink: 0 }} />
          <span>Actualizando historial… puede tardar varios minutos (0,5&nbsp;s por valor).</span>
        </div>
      ) : confirming ? (
        /* Estado: esperando confirmación */
        <div style={{ background: 'var(--bg-input)', borderRadius: 8, padding: 16 }}>
          <p style={{ fontWeight: 600, marginBottom: 10 }}>⚠ Antes de continuar:</p>
          <ul style={{ paddingLeft: 20, marginBottom: 14, fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.7 }}>
            <li>Se descargará el historial de <strong>todos</strong> los valores del catálogo desde Yahoo Finance.</li>
            <li>La operación tarda ~0,5&nbsp;s por valor para evitar rate-limiting. Con 50 valores, unos 25&nbsp;seg.</li>
            <li><strong>No se puede cancelar</strong> una vez iniciada.</li>
            <li>Puedes seguir usando la aplicación mientras se ejecuta en segundo plano.</li>
            <li>Al terminar, los snapshots de precios también se actualizarán.</li>
          </ul>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn-primary btn-sm" onClick={start}>
              Iniciar actualización
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setConfirming(false)}>
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        /* Estado: idle */
        <button
          className="btn-ghost btn-sm"
          onClick={() => { setMsg(null); setErr(null); setConfirming(true) }}
        >
          ⚠ Forzar actualización del historial
        </button>
      )}

      {/* Pie: resultado de la última ejecución */}
      {jobStatus?.finished_at && !running && (
        <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 10 }}>
          Última ejecución: {new Date(jobStatus.finished_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })}
          {' · '}
          {jobStatus.result === 'ok'
            ? <span style={{ color: 'var(--green)' }}>✓ completada</span>
            : <span style={{ color: 'var(--red)' }}>{jobStatus.result}</span>
          }
        </p>
      )}

      {/* ── Rellenar ISINs vacíos ── */}
      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '20px 0 16px' }} />
      <h3 style={{ marginBottom: 8, fontSize: '1rem' }}>Rellenar ISINs que faltan</h3>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: 12 }}>
        Busca el ISIN de cada valor que aún no lo tiene en dos pasadas: 1ª
        coincidencia exacta en Yahoo por ticker; 2ª búsqueda por nombre en
        Business Insider para los que falten (solo acepta el ISIN si no existe ya
        en otro valor). Las cripto se excluyen. Se ejecuta en segundo plano y
        guarda cada ISIN según lo encuentra; no sobrescribe los existentes.
      </p>
      {isinRunning ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          <div className="spinner" style={{ width: 18, height: 18, flexShrink: 0 }} />
          <span>
            Buscando ISINs en Yahoo…
            {isinStatus && (
              <> {isinStatus.checked}/{isinStatus.total} revisados · {isinStatus.updated} rellenados</>
            )}
          </span>
        </div>
      ) : (
        <button className="btn-ghost btn-sm" onClick={fillIsins}>
          Buscar y rellenar ISINs
        </button>
      )}

      {/* Resultado de la última ejecución (también si falló a mitad) */}
      {isinStatus && !isinRunning && (isinStatus.result || isinStatus.finished_at) && (
        <div style={{ marginTop: 10, fontSize: '0.85rem' }}>
          {isinStatus.result && isinStatus.result.startsWith('error') ? (
            <span style={{ color: 'var(--red)' }}>
              ⚠ Falló antes de terminar — se rellenaron {isinStatus.updated} de {isinStatus.checked} revisados.
              {' '}{isinStatus.result}
            </span>
          ) : (
            <span style={{ color: 'var(--green)' }}>
              ✓ {isinStatus.updated} rellenado(s)
              {(isinStatus.updated_pass1 != null) && (
                <span style={{ color: 'var(--text-muted)' }}>
                  {' '}(exacta: {isinStatus.updated_pass1} · heurística: {isinStatus.updated_pass2})
                </span>
              )}
            </span>
          )}
          {isinStatus.skipped_existing?.length > 0 && (
            <p style={{ color: 'var(--text-muted)', marginTop: 6 }}>
              Descartados (el ISIN encontrado ya existía en otro valor): {isinStatus.skipped_existing.join(', ')}
            </p>
          )}
          {isinStatus.not_found?.length > 0 && (
            <p style={{ color: 'var(--text-muted)', marginTop: 6 }}>
              Sin ISIN tras ambas pasadas: {isinStatus.not_found.join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Gestión de mercados (catálogo dinámico)
// ---------------------------------------------------------------------------

const EMPTY_MARKET = { code: '', name: '', index_ticker: '', currency: 'EUR', fiscal_window_days: 60, yahoo_exchange: '', market_type: 'stock' }

function MarketsSection() {
  const { t } = useAppConfig()
  const [markets, setMarkets]   = useState([])
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing]   = useState(null)
  const [form, setForm]         = useState(EMPTY_MARKET)
  const [busy, setBusy]         = useState(false)
  const [err, setErr]           = useState(null)
  const [msg, setMsg]           = useState(null)
  // Explorador por mercado
  const [mktExplorer, setMktExplorer] = useState(null)  // market code abierto, o null
  const [mktYfQuery, setMktYfQuery]   = useState('')
  const [mktYfResults, setMktYfResults] = useState(null)
  const [mktYfLoading, setMktYfLoading] = useState(false)
  const [mktYfError, setMktYfError]     = useState(null)
  const [mktTotal, setMktTotal]         = useState(null)

  async function load() { setMarkets(await api.get('/admin/markets')) }
  useEffect(() => { load() }, [])

  function field(name) {
    return {
      value: form[name],
      onChange: e => setForm(f => ({ ...f, [name]: e.target.value })),
    }
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setErr(null); setMsg(null)
    try {
      const body = { ...form, fiscal_window_days: Number(form.fiscal_window_days) }
      if (!body.index_ticker) delete body.index_ticker
      if (editing) {
        await api.patch(`/admin/markets/${editing.code}`, {
          name: body.name,
          index_ticker: body.index_ticker,
          currency: body.currency,
          fiscal_window_days: body.fiscal_window_days,
          yahoo_exchange: body.yahoo_exchange || null,
          market_type: body.market_type,
        })
        setMsg('Mercado actualizado')
      } else {
        await api.post('/admin/markets', body)
        setMsg('Mercado creado')
      }
      setShowForm(false); setEditing(null); setForm(EMPTY_MARKET)
      await load()
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function del(code) {
    if (!confirm(`¿Eliminar el mercado "${code}"?`)) return
    setErr(null); setMsg(null)
    try {
      await api.delete(`/admin/markets/${code}`)
      await load()
    } catch (e) { setErr(e.message) }
  }

  async function syncCurrency(m) {
    if (!confirm(t('admin.market_sync_currency_confirm').replace('{c}', m.currency).replace('{code}', m.code))) return
    setErr(null); setMsg(null)
    try {
      const r = await api.post(`/admin/markets/${m.code}/sync-currency`)
      setMsg(t('admin.market_sync_currency_done').replace('{n}', r.updated).replace('{c}', r.currency))
      await load()
    } catch (e) { setErr(e.message) }
  }

  function startEdit(m) {
    setEditing(m)
    setForm({ code: m.code, name: m.name, index_ticker: m.index_ticker ?? '', currency: m.currency, fiscal_window_days: m.fiscal_window_days, yahoo_exchange: m.yahoo_exchange ?? '', market_type: m.market_type ?? 'stock' })
    setShowForm(true)
    setErr(null); setMsg(null)
  }

  async function searchMktYahoo(e) {
    e?.preventDefault()
    if (!mktYfQuery.trim() || !mktExplorer) return
    setMktYfLoading(true); setMktYfError(null); setMktYfResults(null)
    try {
      const data = await api.get(`/admin/markets/${mktExplorer}/yahoo-securities?q=${encodeURIComponent(mktYfQuery.trim())}`)
      if (data.error === 'no_exchange_configured') {
        setMktYfError(t('admin.market_no_exchange'))
      } else {
        setMktYfResults(data.results || [])
      }
    } catch (err) { setMktYfError(err.message) }
    finally { setMktYfLoading(false) }
  }

  function openMktExplorer(code) {
    if (mktExplorer === code) { setMktExplorer(null); return }
    setMktExplorer(code); setMktYfQuery(''); setMktYfResults(null); setMktYfError(null)
    setMktTotal(null)
  }

  async function listAllMkt() {
    if (!mktExplorer) return
    setMktYfLoading(true); setMktYfError(null); setMktYfResults(null); setMktTotal(null)
    try {
      const data = await api.get(`/admin/markets/${mktExplorer}/yahoo-list-all`)
      if (data.error === 'no_exchange_configured') {
        setMktYfError(t('admin.market_no_exchange'))
      } else {
        setMktYfResults(data.results || [])
        setMktTotal(data.total ?? (data.results || []).length)
      }
    } catch (err) { setMktYfError(err.message) }
    finally { setMktYfLoading(false) }
  }

  /** Añade un valor de Yahoo directamente al mercado que se está explorando. */
  async function addFromMktExplorer(item) {
    if (!mktExplorer) return
    try {
      await api.post('/securities', {
        name: item.name,
        yahoo_ticker: item.ticker,
        market: mktExplorer,
        currency: item.currency || 'EUR',
      })
      // Marcar como añadido en los resultados sin recargar toda la búsqueda
      setMktYfResults(rs => rs.map(r =>
        r.ticker === item.ticker
          ? { ...r, in_catalog: true, catalog_market: mktExplorer }
          : r
      ))
    } catch (e) { setMktYfError(e.message) }
  }

  /** Mueve un mercado una posición arriba o abajo y persiste el nuevo orden. */
  async function moveMarket(code, direction) {
    const idx = markets.findIndex(m => m.code === code)
    if (direction === 'up'   && idx === 0)                return
    if (direction === 'down' && idx === markets.length - 1) return

    // Construir nuevo orden intercambiando posiciones
    const newList = [...markets]
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1
    ;[newList[idx], newList[swapIdx]] = [newList[swapIdx], newList[idx]]

    // Asignar sort_order = índice para que sea el orden visual
    const reorder = newList.map((m, i) => ({ code: m.code, sort_order: i }))

    setErr(null); setMsg(null)
    try {
      await api.put('/admin/markets/reorder', reorder)
      await load()
    } catch (e) { setErr(e.message) }
  }

  return (
    <div className="card" style={{ marginTop: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Mercados</h2>
        <button className="btn-primary btn-sm" onClick={() => {
          setEditing(null); setForm(EMPTY_MARKET); setShowForm(s => !s); setErr(null); setMsg(null)
        }}>
          {showForm && !editing ? 'Cancelar' : '+ Nuevo mercado'}
        </button>
      </div>

      {err && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{err}</div>}
      {msg && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>{msg}</div>}

      {showForm && (
        <div className="card" style={{ marginBottom: 16, background: 'var(--bg-input)' }}>
          <h3 style={{ marginTop: 0 }}>{editing ? 'Editar mercado' : 'Nuevo mercado'}</h3>
          <form onSubmit={submit}>
            <div className="card-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Código *</label>
                <input type="text" {...field('code')} required disabled={!!editing} placeholder="ibex35" />
              </div>
              <div className="form-group" style={{ flex: 2 }}>
                <label>Nombre *</label>
                <input type="text" {...field('name')} required />
              </div>
            </div>
            <div className="card-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Ticker índice</label>
                <input type="text" {...field('index_ticker')} placeholder="^IBEX" />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Divisa</label>
                <select {...field('currency')}>
                  <option value="EUR">EUR</option>
                  <option value="USD">USD</option>
                </select>
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Ventana fiscal (días)</label>
                <input type="number" min={1} {...field('fiscal_window_days')} style={{ width: 80 }} />
              </div>
            </div>
            <div className="card-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>{t('admin.market_yahoo_exchange')}</label>
                <input type="text" {...field('yahoo_exchange')} placeholder="MCE, NMS, LSE…" />
                <small style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                  {t('admin.market_yahoo_exchange_help')}
                </small>
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>{t('admin.market_type')}</label>
                <select {...field('market_type')}>
                  <option value="stock">{t('seg.stock')}</option>
                  <option value="fund">{t('seg.fund')}</option>
                  <option value="etf">{t('seg.etf')}</option>
                  <option value="crypto">{t('seg.crypto')}</option>
                </select>
                <small style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                  {t('admin.market_type_help')}
                </small>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="btn-ghost btn-sm" onClick={() => { setShowForm(false); setEditing(null) }}>Cancelar</button>
              <button type="submit" className="btn-primary btn-sm" disabled={busy}>{busy ? 'Guardando…' : 'Guardar'}</button>
            </div>
          </form>
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 60 }}>Orden</th>
              <th>Código</th>
              <th>Nombre</th>
              <th>Ticker índice</th>
              <th>Divisa</th>
              <th>Ventana fiscal</th>
              <th>Yahoo Exch.</th>
              <th>{t('admin.market_type')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {markets.map((m, idx) => (
              <tr key={m.code}>
                {/* Botones de reordenación */}
                <td>
                  <div style={{ display: 'flex', gap: 2 }}>
                    <button
                      className="btn-ghost btn-sm"
                      style={{ padding: '1px 6px', fontSize: '0.75rem' }}
                      disabled={idx === 0}
                      onClick={() => moveMarket(m.code, 'up')}
                      title="Subir"
                    >▲</button>
                    <button
                      className="btn-ghost btn-sm"
                      style={{ padding: '1px 6px', fontSize: '0.75rem' }}
                      disabled={idx === markets.length - 1}
                      onClick={() => moveMarket(m.code, 'down')}
                      title="Bajar"
                    >▼</button>
                  </div>
                </td>
                <td><code style={{ fontSize: '0.85rem' }}>{m.code}</code></td>
                <td>{m.name}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{m.index_ticker ?? '—'}</td>
                <td>{m.currency}</td>
                <td className="num">{m.fiscal_window_days}d</td>
                <td style={{ fontSize: '0.82rem', color: m.yahoo_exchange ? 'var(--text)' : 'var(--text-muted)' }}>
                  {m.yahoo_exchange || '—'}
                </td>
                <td style={{ textAlign: 'center' }}>
                  <span className={`badge-asset ${m.market_type ?? 'stock'}`}>
                    {t(`seg.${m.market_type ?? 'stock'}`)}
                  </span>
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                    {m.yahoo_exchange && (
                      <button
                        className={mktExplorer === m.code ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
                        onClick={() => openMktExplorer(m.code)}
                        title={t('admin.market_yahoo_btn')}
                      >🔍</button>
                    )}
                    <button className="btn-ghost btn-sm" onClick={() => syncCurrency(m)} title={t('admin.market_sync_currency')}>💱</button>
                    <button className="btn-ghost btn-sm" onClick={() => startEdit(m)}>✎</button>
                    <button className="btn-danger btn-sm" onClick={() => del(m.code)}>✕</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Panel explorador del mercado seleccionado */}
      {mktExplorer && (() => {
        const m = markets.find(x => x.code === mktExplorer)
        if (!m) return null
        const ph = t('admin.market_yahoo_search_ph')
          .replace('{name}', m.name)
          .replace('{exchange}', m.yahoo_exchange || '')
        return (
          <div style={{
            border: '1px solid var(--accent)', borderRadius: 8,
            padding: 14, marginTop: 12, background: 'var(--bg-input)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <strong style={{ fontSize: '0.9rem' }}>🔍 {m.name} · {m.yahoo_exchange}</strong>
              <button className="btn-ghost btn-sm" onClick={() => setMktExplorer(null)}>✕</button>
            </div>
            <form onSubmit={searchMktYahoo} style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              <input
                type="text"
                value={mktYfQuery}
                onChange={e => setMktYfQuery(e.target.value)}
                placeholder={ph}
                style={{ flex: 1, minWidth: 180 }}
                autoFocus
              />
              <button type="submit" className="btn-primary btn-sm" disabled={mktYfLoading || !mktYfQuery.trim()}>
                {mktYfLoading ? t('admin.yf_searching') : t('admin.yf_search_btn')}
              </button>
              <button type="button" className="btn-ghost btn-sm" disabled={mktYfLoading} onClick={listAllMkt}>
                📋 {t('admin.market_list_all')}
              </button>
            </form>

            {mktYfLoading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: 8 }}>
                <div className="spinner" style={{ width: 16, height: 16, flexShrink: 0 }} />
                <span>{t('admin.market_listing')}</span>
              </div>
            )}

            {mktTotal !== null && mktYfResults && !mktYfLoading && (
              <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 8 }}>
                {t('admin.market_list_count')
                  .replace('{n}', mktTotal)
                  .replace('{missing}', mktYfResults.filter(r => !r.in_catalog).length)}
              </div>
            )}

            {mktYfError && <div className="state-error" style={{ padding: 8, marginBottom: 8 }}>{mktYfError}</div>}
            {mktYfResults !== null && mktYfResults.length === 0 && !mktYfLoading && (
              <div className="state-empty">{t('admin.yf_no_results')}</div>
            )}

            {mktYfResults && mktYfResults.length > 0 && (
              <div className="table-wrap" style={{ maxHeight: 320, overflowY: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>{t('admin.yf_col_ticker')}</th>
                      <th>{t('admin.yf_col_name')}</th>
                      <th>{t('admin.yf_col_type')}</th>
                      <th>{t('admin.yf_col_currency')}</th>
                      <th>{t('admin.yf_col_status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mktYfResults.map(item => (
                      <tr key={item.ticker}>
                        <td className="ticker">{item.ticker}</td>
                        <td style={{ fontSize: '0.85rem', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {item.name}
                        </td>
                        <td>
                          <span className="badge" style={{ fontSize: '0.75rem', background: 'var(--bg-card)' }}>
                            {item.type || '—'}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.85rem' }}>{item.currency || '—'}</td>
                        <td>
                          {item.in_catalog ? (
                            <span style={{ color: 'var(--green)', fontWeight: 600, fontSize: '0.82rem' }}>
                              ✓ {item.catalog_market}
                            </span>
                          ) : (
                            <button
                              type="button"
                              className="btn-primary btn-sm"
                              style={{ fontSize: '0.78rem', padding: '2px 8px' }}
                              onClick={() => addFromMktExplorer(item)}
                            >
                              + {t('admin.yf_add')}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 8, marginBottom: 0 }}>
              {t('admin.market_yahoo_exchange_help')}
            </p>
          </div>
        )
      })()}

      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 8, marginBottom: 0 }}>
        El orden aquí determinará el orden de las pestañas en la sección Mercados.
      </p>
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Catálogo de valores (securities CRUD)
// ---------------------------------------------------------------------------

const EMPTY_SEC = { name: '', isin: '', yahoo_ticker: '', google_ticker: '', market: '', currency: 'EUR' }
function SecuritiesSection() {
  const { currencies: CURRENCIES, t } = useAppConfig()
  const [markets, setMarkets]     = useState([])
  const [securities, setSecs]     = useState([])
  const [marketFilter, setMarketFilter] = useState('all')
  const [secSearch, setSecSearch]       = useState('')
  const [showYfExplorer, setShowYfExplorer] = useState(false)
  const [yfQuery, setYfQuery]               = useState('')
  const [yfResults, setYfResults]           = useState(null)   // null=sin búsqueda, []=vacío
  const [yfLoading, setYfLoading]           = useState(false)
  const [yfError, setYfError]               = useState(null)
  const [showForm, setShowForm]   = useState(false)
  const [editing, setEditing]     = useState(null)
  const [form, setForm]           = useState(EMPTY_SEC)
  const [busy, setBusy]           = useState(false)
  const [err, setErr]             = useState(null)
  const [msg, setMsg]             = useState(null)
  const [splitsFor, setSplitsFor] = useState(null)   // security para SplitsModal

  async function load() {
    const [mks, secs] = await Promise.all([api.get('/markets/list'), api.get('/securities')])
    setMarkets(mks)
    setSecs(secs)
    if (!form.market && mks.length) setForm(f => ({ ...f, market: mks[0].code }))
  }
  useEffect(() => { load() }, [])

  async function searchYahoo(e) {
    e?.preventDefault()
    if (!yfQuery.trim()) return
    setYfLoading(true); setYfError(null); setYfResults(null)
    try {
      const data = await api.get(`/admin/securities/search?q=${encodeURIComponent(yfQuery.trim())}`)
      setYfResults(data)
    } catch (err) {
      setYfError(err.message || t('admin.yf_error'))
    } finally {
      setYfLoading(false)
    }
  }

  function prefillFromYahoo(item) {
    setEditing(null)
    setForm({
      name: item.name,
      isin: '',
      yahoo_ticker: item.ticker,
      google_ticker: '',
      market: marketFilter !== 'all' ? marketFilter : markets[0]?.code ?? '',
      currency: item.currency || 'EUR',
    })
    setShowForm(true)
    setErr(null); setMsg(null)
    // Scroll al formulario
    setTimeout(() => window.scrollTo({ top: 0, behavior: 'smooth' }), 50)
  }

  function field(name) {
    return { value: form[name], onChange: e => setForm(f => ({ ...f, [name]: e.target.value })) }
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setErr(null); setMsg(null)
    try {
      const body = { ...form }
      if (!body.isin) delete body.isin
      if (!body.google_ticker) delete body.google_ticker
      if (editing) {
        await api.patch(`/securities/${editing.id}`, body)
        setMsg('Valor actualizado')
      } else {
        await api.post('/securities', body)
        setMsg('Valor añadido')
      }
      setShowForm(false); setEditing(null)
      setForm(f => ({ ...EMPTY_SEC, market: markets[0]?.code ?? '' }))
      await load()
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function del(id, ticker) {
    if (!confirm(`¿Eliminar ${ticker}?`)) return
    setErr(null); setMsg(null)
    try { await api.delete(`/securities/${id}`); await load() }
    catch (e) { setErr(e.message) }
  }

  function startEdit(s) {
    setEditing(s)
    setForm({ name: s.name, isin: s.isin ?? '', yahoo_ticker: s.yahoo_ticker, google_ticker: s.google_ticker ?? '', market: s.market, currency: s.currency })
    setShowForm(true); setErr(null); setMsg(null)
  }

  return (
    <div className="card" style={{ marginTop: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Catálogo de valores</h2>
        <button className="btn-primary btn-sm" onClick={() => {
          setEditing(null)
          setForm({ ...EMPTY_SEC, market: marketFilter !== 'all' ? marketFilter : markets[0]?.code ?? '' })
          setShowForm(s => !s); setErr(null); setMsg(null)
        }}>
          {showForm && !editing ? 'Cancelar' : '+ Nuevo valor'}
        </button>
      </div>

      {/* ── Explorador Yahoo Finance ──────────────────────────────── */}
      <div style={{ marginBottom: 16 }}>
        <button
          type="button"
          className="btn-ghost btn-sm"
          onClick={() => { setShowYfExplorer(s => !s); setYfResults(null); setYfError(null) }}
          style={{ marginBottom: showYfExplorer ? 10 : 0 }}
        >
          🔍 {t('admin.yf_explorer')} {showYfExplorer ? '▲' : '▼'}
        </button>

        {showYfExplorer && (
          <div style={{
            border: '1px solid var(--border)', borderRadius: 8,
            padding: 14, background: 'var(--bg-input)',
          }}>
            <form onSubmit={searchYahoo} style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <input
                type="text"
                value={yfQuery}
                onChange={e => setYfQuery(e.target.value)}
                placeholder={t('admin.yf_search_placeholder')}
                style={{ flex: 1 }}
                autoFocus
              />
              <button type="submit" className="btn-primary btn-sm" disabled={yfLoading || !yfQuery.trim()}>
                {yfLoading ? t('admin.yf_searching') : t('admin.yf_search_btn')}
              </button>
            </form>

            {yfError && (
              <div className="state-error" style={{ padding: 8, marginBottom: 8 }}>{yfError}</div>
            )}

            {yfResults !== null && yfResults.length === 0 && !yfLoading && (
              <div className="state-empty">{t('admin.yf_no_results')}</div>
            )}

            {yfResults && yfResults.length > 0 && (
              <div className="table-wrap" style={{ maxHeight: 320, overflowY: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>{t('admin.yf_col_ticker')}</th>
                      <th>{t('admin.yf_col_name')}</th>
                      <th>{t('admin.yf_col_exchange')}</th>
                      <th>{t('admin.yf_col_type')}</th>
                      <th>{t('admin.yf_col_currency')}</th>
                      <th>{t('admin.yf_col_status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {yfResults.map(item => (
                      <tr key={item.ticker}>
                        <td className="ticker">{item.ticker}</td>
                        <td style={{ fontSize: '0.85rem', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {item.name}
                        </td>
                        <td style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>{item.exchange || '—'}</td>
                        <td>
                          <span className="badge" style={{ fontSize: '0.75rem', background: 'var(--bg-card)' }}>
                            {item.type || '—'}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.85rem' }}>{item.currency || '—'}</td>
                        <td>
                          {item.in_catalog ? (
                            <span style={{ color: 'var(--green)', fontWeight: 600, fontSize: '0.82rem' }}>
                              ✓ {item.catalog_market}
                            </span>
                          ) : (
                            <button
                              type="button"
                              className="btn-primary btn-sm"
                              style={{ fontSize: '0.78rem', padding: '2px 8px' }}
                              onClick={() => prefillFromYahoo(item)}
                            >
                              + {t('admin.yf_add')}
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
      </div>

      {/* Buscador */}
      <input
        type="text"
        placeholder={t('admin.sec_search')}
        value={secSearch}
        onChange={e => setSecSearch(e.target.value)}
        style={{ marginBottom: 10, width: '100%', maxWidth: 320 }}
      />

      {/* Filtro por mercado */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
        {[{ code: 'all', name: t('admin.filter_all') }, ...markets].map(m => (
          <button
            key={m.code}
            className={marketFilter === m.code ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
            onClick={() => setMarketFilter(m.code)}
          >{m.name}</button>
        ))}
      </div>

      {err && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{err}</div>}
      {msg && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>{msg}</div>}

      {showForm && (
        <div className="card" style={{ marginBottom: 16, background: 'var(--bg-input)' }}>
          <h3 style={{ marginTop: 0 }}>{editing ? 'Editar valor' : 'Nuevo valor'}</h3>
          <form onSubmit={submit}>
            <div className="card-row">
              <div className="form-group" style={{ flex: 2 }}>
                <label>Nombre *</label>
                <input type="text" {...field('name')} required />
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>ISIN</label>
                <input type="text" {...field('isin')} placeholder="ES0144580Y14" />
              </div>
            </div>
            <div className="card-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label>Yahoo Ticker *</label>
                <input type="text" {...field('yahoo_ticker')} required placeholder="SAN.MC" />
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
                  {markets.map(m => <option key={m.code} value={m.code}>{m.name}</option>)}
                </select>
              </div>
              <div className="form-group" style={{ flex: 1 }}>
                <label>Divisa *</label>
                <select {...field('currency')}>
                  {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button type="button" className="btn-ghost btn-sm" onClick={() => { setShowForm(false); setEditing(null) }}>Cancelar</button>
              <button type="submit" className="btn-primary btn-sm" disabled={busy}>{busy ? 'Guardando…' : 'Guardar'}</button>
            </div>
          </form>
        </div>
      )}

      {(() => {
        const q = secSearch.toLowerCase()
        const filtered = securities
          .filter(s => marketFilter === 'all' || s.market === marketFilter)
          .filter(s => !q || s.name.toLowerCase().includes(q) || s.yahoo_ticker.toLowerCase().includes(q))
        const scrollStyle = filtered.length > 10 ? { maxHeight: 540, overflowY: 'auto' } : {}
        if (filtered.length === 0) return (
          <div className="state-empty">No hay valores en el catálogo{marketFilter !== 'all' ? ' para este mercado' : ''}{q ? ` que coincidan con "${secSearch}"` : ''}.</div>
        )
        return (
        <div className="table-wrap" style={scrollStyle}>
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
              {filtered.map(s => (
                <tr key={s.id}>
                  <td className="ticker">{s.yahoo_ticker}</td>
                  <td>{s.name}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{s.isin ?? '—'}</td>
                  <td><span className="badge badge-market">{s.market}</span></td>
                  <td>{s.currency}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                      <button className="btn-ghost btn-sm" onClick={() => setSplitsFor(s)} title="Gestionar splits">
                        ÷ Splits
                      </button>
                      <button className="btn-ghost btn-sm" onClick={() => startEdit(s)}>✎</button>
                      <button className="btn-danger btn-sm" onClick={() => del(s.id, s.yahoo_ticker)}>✕</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )
      })()}

      {splitsFor && (
        <SplitsModal
          security={splitsFor}
          onClose={() => setSplitsFor(null)}
        />
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Sección: Solicitudes de usuarios para agregar productos (v1.12.0)
// ---------------------------------------------------------------------------

function RequestsSection({ onCountChanged }) {
  const { t } = useAppConfig()
  const [requests, setRequests]       = useState([])
  const [markets, setMarkets]         = useState([])
  const [reviewing, setReviewing]     = useState(null)  // SecurityRequestRow seleccionada
  const [approveMarket, setApproveMarket] = useState('')
  const [notes, setNotes]             = useState('')
  const [busy, setBusy]               = useState(false)
  const [err, setErr]                 = useState(null)
  const [filter, setFilter]           = useState('pending')

  async function load() {
    try {
      const [reqs, mks] = await Promise.all([
        api.get(`/admin/catalog/requests?req_status=${filter}`),
        api.get('/admin/markets'),
      ])
      setRequests(reqs || [])
      setMarkets(mks || [])
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { load() }, [filter])

  function openReview(req) {
    setReviewing(req)
    setApproveMarket(req.market_id || '')
    setNotes('')
    setErr(null)
  }

  async function doApprove() {
    if (!approveMarket) { setErr(t('admin.approve_market_label') + ' requerido'); return }
    setBusy(true); setErr(null)
    try {
      await api.patch(`/admin/catalog/requests/${reviewing.id}/approve`, {
        market_id: approveMarket,
        notes: notes.trim() || null,
      })
      setReviewing(null)
      await load()
      onCountChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  async function doReject() {
    setBusy(true); setErr(null)
    try {
      await api.patch(`/admin/catalog/requests/${reviewing.id}/reject`, {
        notes: notes.trim() || null,
      })
      setReviewing(null)
      await load()
      onCountChanged?.()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  function statusChip(status) {
    const colors = { pending: '#d97706', approved: 'var(--green)', rejected: 'var(--red)' }
    const labels = {
      pending: t('admin.status_pending'),
      approved: t('admin.status_approved'),
      rejected: t('admin.status_rejected'),
    }
    return (
      <span style={{
        background: colors[status] || 'var(--text-muted)',
        color: '#fff', borderRadius: 4, padding: '1px 7px', fontSize: '0.75rem',
      }}>
        {labels[status] || status}
      </span>
    )
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem' }}>{t('admin.requests_section')}</h2>
        <div style={{ display: 'flex', gap: 6 }}>
          {['pending', 'approved', 'rejected', 'all'].map(f => (
            <button key={f} className={filter === f ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
              onClick={() => setFilter(f)}>
              {f === 'all' ? 'Todas' : t(`admin.status_${f}`)}
            </button>
          ))}
        </div>
      </div>

      {err && <div className="state-error" style={{ marginBottom: 10 }}>{err}</div>}

      {requests.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>{t('admin.requests_empty')}</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('admin.col_user')}</th>
                <th>{t('admin.col_ticker')}</th>
                <th>{t('admin.col_name')}</th>
                <th>{t('admin.col_market')}</th>
                <th>{t('admin.col_status')}</th>
                <th>{t('admin.col_date')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {requests.map(req => (
                <tr key={req.id}>
                  <td>{req.username || req.user_id}</td>
                  <td><strong>{req.ticker}</strong></td>
                  <td style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{req.name}</td>
                  <td>{req.market_id || '—'}</td>
                  <td>{statusChip(req.status)}</td>
                  <td style={{ fontSize: '0.78rem', whiteSpace: 'nowrap' }}>
                    {req.created_at ? new Date(req.created_at).toLocaleDateString('es-ES') : '—'}
                  </td>
                  <td>
                    {req.status === 'pending' && (
                      <button className="btn-ghost btn-sm" onClick={() => openReview(req)}>
                        {t('admin.review_title')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal de revisión */}
      {reviewing && (
        <div className="modal-backdrop" onClick={() => !busy && setReviewing(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <h2 style={{ marginBottom: 14 }}>{t('admin.review_title')}</h2>
            <div style={{ marginBottom: 14, fontSize: '0.88rem', display: 'grid', gridTemplateColumns: '100px 1fr', gap: '4px 8px' }}>
              <span style={{ color: 'var(--text-muted)' }}>{t('admin.col_user')}:</span><span>{reviewing.username}</span>
              <span style={{ color: 'var(--text-muted)' }}>Ticker:</span><span><strong>{reviewing.ticker}</strong></span>
              <span style={{ color: 'var(--text-muted)' }}>{t('admin.col_name')}:</span><span>{reviewing.name}</span>
              {reviewing.isin && <><span style={{ color: 'var(--text-muted)' }}>ISIN:</span><span>{reviewing.isin}</span></>}
              {reviewing.currency && <><span style={{ color: 'var(--text-muted)' }}>Divisa:</span><span>{reviewing.currency}</span></>}
            </div>

            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: '0.85rem' }}>{t('admin.approve_market_label')} *</label>
              <select className="input" value={approveMarket} onChange={e => setApproveMarket(e.target.value)}
                disabled={busy} style={{ width: '100%' }}>
                <option value="">— seleccionar —</option>
                {markets.map(m => <option key={m.code} value={m.code}>{m.name} ({m.code})</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: '0.85rem' }}>{t('admin.notes_label')}</label>
              <textarea className="input" rows={3} value={notes} onChange={e => setNotes(e.target.value)}
                placeholder={t('admin.notes_placeholder')} disabled={busy} style={{ width: '100%', resize: 'vertical' }} />
            </div>

            {err && <div className="state-error" style={{ marginBottom: 10 }}>{err}</div>}

            <div className="modal-actions">
              <button className="btn-ghost" onClick={() => setReviewing(null)} disabled={busy}>
                {t('requests.cancel')}
              </button>
              <button className="btn-danger" onClick={doReject} disabled={busy}>
                {t('admin.reject_btn')}
              </button>
              <button className="btn-primary" onClick={doApprove} disabled={busy || !approveMarket}>
                {t('admin.approve_btn')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Sección: Mensajes de usuarios al admin (v1.12.0)
// ---------------------------------------------------------------------------

function UserMessagesSection({ onCountChanged }) {
  const { t } = useAppConfig()
  const [messages, setMessages]       = useState([])
  const [err, setErr]                 = useState(null)
  const [showResolved, setShowResolved] = useState(false)
  const [replyingId, setReplyingId]   = useState(null)
  const [replyText, setReplyText]     = useState('')
  const [replyBusy, setReplyBusy]     = useState(false)
  const [replyErr, setReplyErr]       = useState(null)

  async function load() {
    try {
      const data = await api.get('/admin/catalog/messages')
      setMessages(data)
      onCountChanged?.()
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { load() }, [])

  async function resolve(id) {
    try {
      await api.patch(`/admin/catalog/messages/${id}/resolve`)
      setMessages(ms => ms.map(m => m.id === id ? { ...m, is_resolved: true } : m))
      onCountChanged?.()
    } catch (e) { setErr(e.message) }
  }

  function startReply(id) {
    setReplyingId(id)
    setReplyText('')
    setReplyErr(null)
  }

  async function sendReply(id) {
    if (!replyText.trim()) return
    setReplyBusy(true); setReplyErr(null)
    try {
      const updated = await api.post(`/admin/catalog/messages/${id}/reply`, { reply: replyText.trim() })
      setMessages(ms => ms.map(m => m.id === id ? updated : m))
      setReplyingId(null)
      onCountChanged?.()
    } catch (e) { setReplyErr(e.message) }
    finally { setReplyBusy(false) }
  }

  const visible = showResolved ? messages : messages.filter(m => !m.is_resolved)

  return (
    <div className="card" style={{ marginTop: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem' }}>{t('admin.messages_section')}</h2>
        <label style={{ fontSize: '0.82rem', display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer' }}>
          <input type="checkbox" checked={showResolved} onChange={e => setShowResolved(e.target.checked)} />
          {t('admin.messages_show_resolved')}
        </label>
      </div>

      {err && <div className="state-error" style={{ marginBottom: 10 }}>{err}</div>}

      {visible.length === 0 ? (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>{t('admin.messages_empty')}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {visible.map(msg => (
            <div key={msg.id} style={{
              border: '1px solid var(--border)', borderRadius: 6, padding: '10px 14px',
              opacity: msg.is_resolved ? 0.6 : 1,
            }}>
              {/* Cabecera del mensaje */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                  <strong>{msg.username || `user#${msg.user_id}`}</strong>
                  {' · '}
                  {msg.created_at ? new Date(msg.created_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' }) : ''}
                  {msg.subject && (
                    <span style={{
                      marginLeft: 8, background: 'var(--surface-2, #1e293b)', color: 'var(--text-muted)',
                      borderRadius: 4, padding: '1px 6px', fontSize: '0.75rem', border: '1px solid var(--border)',
                    }}>
                      {msg.subject}
                    </span>
                  )}
                  {msg.security_request_id && (
                    <span style={{
                      marginLeft: 4, background: 'var(--accent-soft, #e0e7ff)', color: 'var(--accent)',
                      borderRadius: 4, padding: '0 6px', fontSize: '0.75rem',
                    }}>
                      {t('admin.reply_badge')}
                    </span>
                  )}
                </div>
                {!msg.is_resolved && (
                  <div style={{ display: 'flex', gap: 6 }}>
                    {!msg.admin_reply && replyingId !== msg.id && (
                      <button className="btn-primary btn-sm" style={{ fontSize: '0.75rem' }} onClick={() => startReply(msg.id)}>
                        {t('admin.reply_btn')}
                      </button>
                    )}
                    <button className="btn-ghost btn-sm" style={{ fontSize: '0.75rem' }} onClick={() => resolve(msg.id)}>
                      {t('admin.resolve_btn')}
                    </button>
                  </div>
                )}
              </div>

              {/* Texto del mensaje */}
              <div style={{ fontSize: '0.88rem', whiteSpace: 'pre-wrap', marginBottom: 6 }}>{msg.message}</div>

              {/* Respuesta del admin ya enviada */}
              {msg.admin_reply && (
                <div style={{
                  marginTop: 8, padding: '8px 10px', borderRadius: 4,
                  background: 'var(--surface-2, #1e2a3a)', borderLeft: '3px solid var(--accent)',
                  fontSize: '0.85rem',
                }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                    {t('admin.reply_sent_label')}
                    {msg.admin_reply_at ? ` · ${new Date(msg.admin_reply_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })}` : ''}
                  </div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{msg.admin_reply}</div>
                </div>
              )}

              {/* Formulario de respuesta inline */}
              {replyingId === msg.id && (
                <div style={{ marginTop: 10 }}>
                  {replyErr && <div style={{ color: 'var(--red)', fontSize: '0.8rem', marginBottom: 6 }}>{replyErr}</div>}
                  <textarea
                    className="input"
                    rows={3}
                    value={replyText}
                    onChange={e => setReplyText(e.target.value)}
                    placeholder={t('admin.reply_placeholder')}
                    disabled={replyBusy}
                    style={{ width: '100%', marginBottom: 8, resize: 'vertical', fontSize: '0.88rem' }}
                    autoFocus
                  />
                  <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                    <button className="btn-ghost btn-sm" onClick={() => setReplyingId(null)} disabled={replyBusy}>
                      {t('admin.cancel')}
                    </button>
                    <button className="btn-primary btn-sm" onClick={() => sendReply(msg.id)}
                      disabled={replyBusy || !replyText.trim()}>
                      {replyBusy ? t('admin.sending') : t('admin.reply_send_btn')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
//  Panel principal
// ---------------------------------------------------------------------------

export default function AdminPanel() {
  const { user: me, logout } = useAuth()
  const { appName, t } = useAppConfig()
  const [tab, setTab] = useState('usuarios')
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [opError, setOpError] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [changingPw, setChangingPw] = useState(null)
  const [statusModal, setStatusModal] = useState(null)   // usuario para enable/disable
  const [expiryModal, setExpiryModal] = useState(null)   // usuario para fijar caducidad
  const [historyModal, setHistoryModal] = useState(null) // usuario para ver historial
  const [notifModal, setNotifModal] = useState(null)     // { userId, username } | null
  const [emailModal, setEmailModal] = useState(null)    // usuario para editar email

  const [pwForm, setPwForm] = useState({ current: '', newPw: '', confirm: '' })
  const [userSearch, setUserSearch] = useState('')

  // Backup admin
  const adminFileRef                        = useRef(null)
  const [adminImporting, setAdminImporting] = useState(false)
  const [adminBackupMsg, setAdminBackupMsg] = useState(null)
  const [adminBackupErr, setAdminBackupErr] = useState(null)

  // Catálogo de valores
  const catalogFileRef                        = useRef(null)
  const [catalogImporting, setCatalogImporting] = useState(false)
  const [catalogMsg, setCatalogMsg]             = useState(null)
  const [catalogErr, setCatalogErr]             = useState(null)
  const [pwBusy, setPwBusy] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const [pendingMsgCount, setPendingMsgCount] = useState(0)
  const [pwError, setPwError] = useState(null)
  const [pwOk, setPwOk] = useState(false)

  async function changeOwnPassword(e) {
    e.preventDefault()
    setPwError(null); setPwOk(false)
    if (pwForm.newPw.length < 8) { setPwError('Mínimo 8 caracteres'); return }
    if (pwForm.newPw !== pwForm.confirm) { setPwError('Las contraseñas no coinciden'); return }
    setPwBusy(true)
    try {
      await api.patch('/auth/password', { current_password: pwForm.current, new_password: pwForm.newPw })
      setPwForm({ current: '', newPw: '', confirm: '' })
      setPwOk(true)
    } catch (err) { setPwError(err.message) }
    finally { setPwBusy(false) }
  }

  async function exportAdminBackup() {
    setAdminBackupErr(null)
    const res = await fetch('/api/admin/backup/export', { credentials: 'include' })
    if (!res.ok) { setAdminBackupErr('Error al exportar'); return }
    const blob = await res.blob()
    const cd = res.headers.get('Content-Disposition') ?? ''
    const match = cd.match(/filename="([^"]+)"/)
    const filename = match ? match[1] : 'finanzas_admin_backup.json'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  async function importAdminBackup(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setAdminImporting(true); setAdminBackupErr(null); setAdminBackupMsg(null)
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const r = await api.post('/admin/backup/import', data)
      setAdminBackupMsg(
        `Importado: ${r.users_created} usuarios nuevos, ` +
        `${r.securities_created} valores nuevos (${r.securities_updated} actualizados), ` +
        `${r.positions_found} posiciones, ` +
        `${r.transactions_added} transacciones, ` +
        `${r.dividends_added} dividendos, ` +
        `${r.favorites_added} favoritos.` +
        (r.errors?.length ? ` Avisos: ${r.errors.join('; ')}` : '')
      )
      loadUsers()
    } catch (err) {
      setAdminBackupErr(err.message ?? 'Error al importar')
    } finally {
      setAdminImporting(false)
      e.target.value = ''
    }
  }

  async function exportCatalog() {
    setCatalogErr(null)
    try {
      const res = await fetch('/api/admin/catalog/export', { credentials: 'include' })
      if (!res.ok) { setCatalogErr('Error al exportar el catálogo'); return }
      const blob = await res.blob()
      const cd   = res.headers.get('Content-Disposition') ?? ''
      const match = cd.match(/filename="([^"]+)"/)
      const filename = match ? match[1] : 'catalogo_valores.json'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = filename; a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setCatalogErr(err.message ?? 'Error al exportar')
    }
  }

  async function importCatalog(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setCatalogImporting(true); setCatalogErr(null); setCatalogMsg(null)
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const r = await api.post('/admin/catalog/import', data)
      const noMkt = r.securities_no_market > 0
        ? `, ${r.securities_no_market} sin mercado`
        : ''
      setCatalogMsg(
        `Mercados: ${r.markets_imported} importados, ${r.markets_skipped} ya existían. ` +
        `Valores: ${r.securities_imported} importados, ${r.securities_skipped} ya existían${noMkt}.`
      )
    } catch (err) {
      setCatalogErr(err.message ?? 'Error al importar')
    } finally {
      setCatalogImporting(false)
      e.target.value = ''
    }
  }

  async function loadUsers() {
    setLoading(true)
    try {
      setUsers(await api.get('/admin/users'))
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  async function loadPendingCount() {
    try {
      const data = await api.get('/admin/catalog/requests/pending-count')
      setPendingCount(data?.count ?? 0)
    } catch { /* ignorar */ }
  }

  async function loadPendingMsgCount() {
    try {
      const data = await api.get('/admin/catalog/messages/pending-count')
      setPendingMsgCount(data?.count ?? 0)
    } catch { /* ignorar */ }
  }

  useEffect(() => { loadUsers(); loadPendingCount(); loadPendingMsgCount() }, [])

  async function deleteUser(u) {
    if (!confirm(`¿Eliminar al usuario "${u.username}"? Esta acción no se puede deshacer.`)) return
    setOpError(null)
    try {
      await api.delete(`/admin/users/${u.id}`)
      setUsers(us => us.filter(x => x.id !== u.id))
    } catch (err) { setOpError(err.message) }
  }

  async function toggleRole(u) {
    const newRole = !u.is_admin
    const label = newRole ? 'administrador' : 'usuario normal'
    if (!confirm(`¿Cambiar "${u.username}" a ${label}?`)) return
    setOpError(null)
    try {
      const updated = await api.patch(`/admin/users/${u.id}/role`, { is_admin: newRole })
      setUsers(us => us.map(x => x.id === u.id ? updated : x))
    } catch (err) { setOpError(err.message) }
  }

  if (loading) return <div className="state-loading" style={{ minHeight: '100vh' }}><div className="spinner" /></div>
  if (error)   return <div className="state-error">{error}</div>

  const TABS = [
    { key: 'usuarios',      label: t('admin.tab_users')   },
    { key: 'catalogo',      label: t('admin.tab_catalog') },
    { key: 'configuracion', label: t('admin.tab_config')  },
    { key: 'herramientas',  label: t('admin.tab_tools')   },
  ]

  return (
    <div style={{ maxWidth: 820, margin: '0 auto', padding: '24px 16px' }}>
      {/* Cabecera */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.4rem' }}>Administración</h1>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{appName} · {me?.username}</span>
        </div>
        <button className="btn-ghost btn-sm" onClick={logout}>Salir</button>
      </div>

      {/* Barra de pestañas */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20, flexWrap: 'wrap' }}>
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            className={tab === key ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
            onClick={() => setTab(key)}
            style={{ position: 'relative' }}
          >
            {label}
            {key === 'catalogo' && pendingCount > 0 && (
              <span style={{
                position: 'absolute', top: -4, right: -4,
                background: 'var(--red, #dc2626)', color: '#fff',
                borderRadius: '50%', width: 16, height: 16,
                fontSize: '0.6rem', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700, animation: 'pulse 1.5s infinite',
              }}>
                {pendingCount > 9 ? '9+' : pendingCount}
              </span>
            )}
            {key === 'usuarios' && pendingMsgCount > 0 && (
              <span style={{
                position: 'absolute', top: -4, right: -4,
                background: 'var(--red, #dc2626)', color: '#fff',
                borderRadius: '50%', width: 16, height: 16,
                fontSize: '0.6rem', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700, animation: 'pulse 1.5s infinite',
              }}>
                {pendingMsgCount > 9 ? '9+' : pendingMsgCount}
              </span>
            )}
          </button>
        ))}
      </div>

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

      {/* ── Pestaña: Usuarios ─────────────────────────────────────────── */}
      {tab === 'usuarios' && <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Usuarios ({users.length})</h2>
          <button className="btn-primary btn-sm" onClick={() => setShowCreate(true)}>+ Nuevo usuario</button>
        </div>
        <input
          type="text"
          placeholder={t('admin.user_search')}
          value={userSearch}
          onChange={e => setUserSearch(e.target.value)}
          style={{ marginBottom: 12, width: '100%', maxWidth: 280 }}
        />
        {(() => {
          const filtered = users.filter(u =>
            u.username.toLowerCase().includes(userSearch.toLowerCase())
          )
          const scrollStyle = filtered.length > 10
            ? { maxHeight: 540, overflowY: 'auto' }
            : {}
          return (
        <div className="table-wrap" style={scrollStyle}>
          <table>
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Actividad</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(u => (
                <tr key={u.id}>
                  {/* Columna 1: identidad */}
                  <td style={{ verticalAlign: 'top' }}>
                    <div style={{ fontWeight: u.id === me?.id ? 700 : 500, marginBottom: 4 }}>
                      {u.username}
                      {u.id === me?.id && (
                        <span style={{ marginLeft: 6, fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 400 }}>(tú)</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      <span className="badge" style={{
                        background: u.is_admin ? 'var(--accent)' : 'var(--bg-input)',
                        color: u.is_admin ? '#fff' : 'var(--text-muted)',
                      }}>
                        {u.is_admin ? 'Admin' : 'Usuario'}
                      </span>
                      <StatusBadge enabled={u.is_enabled} />
                    </div>
                    {u.expires_at && (
                      <div style={{ fontSize: '0.73rem', color: 'var(--text-muted)', marginTop: 4 }}>
                        Caduca: {fmt(u.expires_at)}
                      </div>
                    )}
                    {u.email && (
                      <div style={{ fontSize: '0.73rem', color: 'var(--text-muted)', marginTop: 4 }}>
                        ✉ {u.email}
                      </div>
                    )}
                  </td>

                  {/* Columna 2: actividad */}
                  <td style={{ verticalAlign: 'top', fontSize: '0.78rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                    <div>Alta: {fmt(u.created_at)}</div>
                    <div>{t('admin.user_last_login')}: {u.last_login_at ? fmt(u.last_login_at) : t('admin.never')}</div>
                    <div>
                      {t('admin.user_operations')}:{' '}
                      <span style={{ color: u.has_operations ? 'var(--green)' : 'var(--text-muted)', fontWeight: 600 }}>
                        {u.has_operations ? 'Sí' : 'No'}
                      </span>
                    </div>
                  </td>

                  {/* Columna 3: acciones */}
                  <td style={{ verticalAlign: 'top' }}>
                    <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                      <button className="btn-ghost btn-sm" onClick={() => setChangingPw(u)}>
                        Contraseña
                      </button>
                      <button className="btn-ghost btn-sm" onClick={() => setHistoryModal(u)} title="Ver historial de estados">
                        Historial
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setNotifModal({ userId: u.id, username: u.username })}
                        title={t('admin.notif_send_btn')}
                      >
                        {t('admin.notif_send_btn')}
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setEmailModal(u)}
                        title={t('admin.email_edit_label')}
                      >
                        {t('admin.email_edit_label')}
                      </button>
                      {u.id !== me?.id && (
                        <>
                          <button
                            className={u.is_enabled ? 'btn-danger btn-sm' : 'btn-primary btn-sm'}
                            onClick={() => setStatusModal(u)}
                            title={u.is_enabled ? 'Deshabilitar usuario' : 'Habilitar usuario'}
                          >
                            {u.is_enabled ? 'Deshabilitar' : 'Habilitar'}
                          </button>
                          <button className="btn-ghost btn-sm" onClick={() => setExpiryModal(u)} title="Fecha de caducidad">
                            Caducidad
                          </button>
                          <button
                            className="btn-ghost btn-sm"
                            onClick={() => toggleRole(u)}
                            title={u.is_admin ? 'Quitar admin' : 'Hacer admin'}
                          >
                            {u.is_admin ? '↓ Usuario' : '↑ Admin'}
                          </button>
                          <button className="btn-danger btn-sm" onClick={() => deleteUser(u)}>
                            Eliminar
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
          )
        })()}
      </div>}

      {tab === 'usuarios' && <div className="card" style={{ marginTop: 24 }}>
        <h2>Cambiar mi contraseña</h2>
        {pwError && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{pwError}</div>}
        {pwOk    && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12 }}>Contraseña actualizada correctamente.</div>}
        <form onSubmit={changeOwnPassword}>
          <div className="form-group">
            <label>Contraseña actual</label>
            <input
              type="password"
              value={pwForm.current}
              onChange={e => setPwForm(f => ({ ...f, current: e.target.value }))}
              required
            />
          </div>
          <div className="form-group">
            <label>Nueva contraseña</label>
            <input
              type="password"
              value={pwForm.newPw}
              onChange={e => setPwForm(f => ({ ...f, newPw: e.target.value }))}
              required
              minLength={8}
            />
          </div>
          <div className="form-group">
            <label>Repetir nueva contraseña</label>
            <input
              type="password"
              value={pwForm.confirm}
              onChange={e => setPwForm(f => ({ ...f, confirm: e.target.value }))}
              required
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button type="submit" className="btn-primary btn-sm" disabled={pwBusy}>
              {pwBusy ? 'Guardando…' : 'Cambiar contraseña'}
            </button>
          </div>
        </form>
      </div>}

      {tab === 'usuarios' && (
        <div className="card" style={{ marginTop: 24 }}>
          <h2 style={{ marginBottom: 8 }}>{t('admin.broadcast_section_title')}</h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 12 }}>
            {t('admin.broadcast_section_desc')}
          </p>
          <button
            className="btn-primary btn-sm"
            onClick={() => setNotifModal({ userId: null, username: null })}
          >
            {t('admin.broadcast_btn')}
          </button>
        </div>
      )}

      {tab === 'usuarios' && (
        <UserMessagesSection onCountChanged={loadPendingMsgCount} />
      )}

      {/* ── Pestaña: Herramientas ─────────────────────────────────────── */}
      {tab === 'herramientas' && <EmailConfigSection />}

      {tab === 'herramientas' && <div className="card" style={{ marginTop: 24 }}>
        <h2>Backup completo del sistema</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: '0.9rem' }}>
          Exporta todos los usuarios, el catálogo de valores y todas las carteras a un JSON.
          La importación es idempotente: crea lo que no existe y omite lo que ya está.
        </p>
        {adminBackupErr && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{adminBackupErr}</div>}
        {adminBackupMsg && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12, fontSize: '0.85rem' }}>{adminBackupMsg}</div>}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <button className="btn-primary btn-sm" onClick={exportAdminBackup}>
            ↓ Exportar backup completo
          </button>
          <button
            className="btn-ghost btn-sm"
            disabled={adminImporting}
            onClick={() => adminFileRef.current?.click()}
          >
            {adminImporting ? 'Importando…' : '↑ Importar backup'}
          </button>
          <input
            ref={adminFileRef}
            type="file"
            accept=".json,application/json"
            style={{ display: 'none' }}
            onChange={importAdminBackup}
          />
        </div>
      </div>}

      {tab === 'herramientas' && <div className="card" style={{ marginTop: 24 }}>
        <h2>Catálogo de valores</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 16, fontSize: '0.9rem' }}>
          Exporta o importa el catálogo de mercados y valores en formato JSON.
          Útil para copiar el catálogo entre servidores.<br />
          <strong>Índice de deduplicación:</strong> Yahoo Ticker (único global).
          Si un valor ya existe en cualquier mercado no se sobreescribe.
        </p>
        {catalogErr && <div className="state-error" style={{ padding: 8, marginBottom: 12 }}>{catalogErr}</div>}
        {catalogMsg && <div style={{ color: 'var(--green)', padding: 8, marginBottom: 12, fontSize: '0.85rem' }}>{catalogMsg}</div>}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <button className="btn-primary btn-sm" onClick={exportCatalog}>
            ↓ Exportar catálogo
          </button>
          <button
            className="btn-ghost btn-sm"
            disabled={catalogImporting}
            onClick={() => catalogFileRef.current?.click()}
          >
            {catalogImporting ? 'Importando…' : '↑ Importar catálogo'}
          </button>
          <input
            ref={catalogFileRef}
            type="file"
            accept=".json,application/json"
            style={{ display: 'none' }}
            onChange={importCatalog}
          />
        </div>
      </div>}

      {tab === 'herramientas' && <ForceHistoryUpdateSection />}

      {/* ── Pestaña: Catálogo ─────────────────────────────────────────── */}
      {tab === 'catalogo' && <MarketsSection />}
      {tab === 'catalogo' && <SecuritiesSection />}
      {tab === 'catalogo' && <RequestsSection onCountChanged={loadPendingCount} />}

      {/* ── Pestaña: Configuración ────────────────────────────────────── */}
      {tab === 'configuracion' && <ConfigSection />}

      {/* Modales */}
      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); loadUsers() }}
        />
      )}
      {changingPw && (
        <ChangePasswordModal
          user={changingPw}
          onClose={() => setChangingPw(null)}
          onDone={() => setChangingPw(null)}
        />
      )}
      {statusModal && (
        <UserStatusModal
          user={statusModal}
          onClose={() => setStatusModal(null)}
          onDone={() => { setStatusModal(null); loadUsers() }}
        />
      )}
      {expiryModal && (
        <ExpiryModal
          user={expiryModal}
          onClose={() => setExpiryModal(null)}
          onDone={() => { setExpiryModal(null); loadUsers() }}
        />
      )}
      {historyModal && (
        <UserHistoryModal
          user={historyModal}
          onClose={() => setHistoryModal(null)}
        />
      )}
      {notifModal && (
        <SendNotificationModal
          userId={notifModal.userId}
          username={notifModal.username}
          onClose={() => setNotifModal(null)}
          onSent={() => setNotifModal(null)}
        />
      )}
      {emailModal && (
        <EditEmailModal
          user={emailModal}
          onClose={() => setEmailModal(null)}
          onDone={() => { setEmailModal(null); loadUsers() }}
        />
      )}
    </div>
  )
}
