import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useAppConfig } from '../context/AppContext'

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
  const [form, setForm] = useState({ username: '', password: '', is_admin: false })
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
      await api.post('/admin/users', { ...form, username: form.username.trim() })
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

  useEffect(() => { loadUsers() }, [])

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
          >
            {label}
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
                <th>Rol</th>
                <th>Estado</th>
                <th>Caduca</th>
                <th>Creado</th>
                <th>{t('admin.user_last_login')}</th>
                <th>{t('admin.user_operations')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(u => (
                <tr key={u.id}>
                  <td>
                    <span style={{ fontWeight: u.id === me?.id ? 600 : 400 }}>{u.username}</span>
                    {u.id === me?.id && <span style={{ marginLeft: 6, fontSize: '0.75rem', color: 'var(--text-muted)' }}>(tú)</span>}
                  </td>
                  <td>
                    <span
                      className="badge"
                      style={{
                        background: u.is_admin ? 'var(--accent)' : 'var(--bg-input)',
                        color: u.is_admin ? '#fff' : 'var(--text-muted)',
                      }}
                    >
                      {u.is_admin ? 'Admin' : 'Usuario'}
                    </span>
                  </td>
                  <td><StatusBadge enabled={u.is_enabled} /></td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {u.expires_at ? fmt(u.expires_at) : '—'}
                  </td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{fmt(u.created_at)}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {u.last_login_at ? fmt(u.last_login_at) : t('admin.never')}
                  </td>
                  <td>
                    <span style={{
                      fontSize: '0.8rem', fontWeight: 600,
                      color: u.has_operations ? 'var(--green)' : 'var(--text-muted)',
                    }}>
                      {u.has_operations ? 'Sí' : 'No'}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setChangingPw(u)}
                      >
                        Contraseña
                      </button>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setHistoryModal(u)}
                        title="Ver historial de estados"
                      >
                        Historial
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
                          <button
                            className="btn-ghost btn-sm"
                            onClick={() => setExpiryModal(u)}
                            title="Fecha de caducidad"
                          >
                            Caducidad
                          </button>
                          <button
                            className="btn-ghost btn-sm"
                            onClick={() => toggleRole(u)}
                            title={u.is_admin ? 'Quitar admin' : 'Hacer admin'}
                          >
                            {u.is_admin ? '↓ Usuario' : '↑ Admin'}
                          </button>
                          <button
                            className="btn-danger btn-sm"
                            onClick={() => deleteUser(u)}
                          >
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

      {/* ── Pestaña: Herramientas ─────────────────────────────────────── */}
      {tab === 'herramientas' && <div className="card" style={{ marginTop: 0 }}>
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
    </div>
  )
}
