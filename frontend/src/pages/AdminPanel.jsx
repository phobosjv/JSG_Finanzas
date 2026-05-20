import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'

function fmt(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleDateString('es-ES')
}

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

export default function AdminPanel() {
  const { user: me, logout } = useAuth()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [opError, setOpError] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [changingPw, setChangingPw] = useState(null)

  const [pwForm, setPwForm] = useState({ current: '', newPw: '', confirm: '' })

  // Backup admin
  const adminFileRef                        = useRef(null)
  const [adminImporting, setAdminImporting] = useState(false)
  const [adminBackupMsg, setAdminBackupMsg] = useState(null)
  const [adminBackupErr, setAdminBackupErr] = useState(null)
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

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', padding: '24px 16px' }}>
      {/* Cabecera */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.4rem' }}>Administración</h1>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{me?.username}</span>
        </div>
        <button className="btn-ghost btn-sm" onClick={logout}>Salir</button>
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

      {/* Tabla de usuarios */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 style={{ margin: 0 }}>Usuarios ({users.length})</h2>
          <button className="btn-primary btn-sm" onClick={() => setShowCreate(true)}>+ Nuevo usuario</button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Usuario</th>
                <th>Rol</th>
                <th>Creado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td className="num" style={{ color: 'var(--text-muted)' }}>{u.id}</td>
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
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{fmt(u.created_at)}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <button
                        className="btn-ghost btn-sm"
                        onClick={() => setChangingPw(u)}
                      >
                        Contraseña
                      </button>
                      {u.id !== me?.id && (
                        <>
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
      </div>

      {/* Cambiar mi contraseña */}
      <div className="card" style={{ marginTop: 24 }}>
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
      </div>

      {/* Backup completo del sistema */}
      <div className="card" style={{ marginTop: 24 }}>
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
      </div>

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
    </div>
  )
}
