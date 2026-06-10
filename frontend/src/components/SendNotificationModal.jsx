import { useState } from 'react'
import { api } from '../api/client'
import { useAppConfig } from '../context/AppContext'

/**
 * Modal para que el admin envíe una notificación personalizada.
 *
 * Props:
 *   userId   — number | null. Si es null → broadcast a todos los usuarios.
 *   username — string | null. Nombre del destinatario (para mostrar en el título).
 *   onClose()   — cierra el modal.
 *   onSent(n)   — callback tras envío exitoso; recibe el número de notificaciones enviadas.
 */
export default function SendNotificationModal({ userId = null, username = null, onClose, onSent }) {
  const { t } = useAppConfig()
  const [title, setTitle]     = useState('')
  const [body, setBody]       = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError]     = useState('')
  const [sent, setSent]       = useState(null)  // número de envíos, null = aún no enviado

  function handleBackdrop(e) {
    if (e.target === e.currentTarget) onClose()
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!title.trim() || !body.trim()) return
    setSending(true)
    setError('')
    try {
      const data = await api.post('/admin/notifications/send', {
        user_id: userId,
        title: title.trim(),
        body: body.trim(),
      })
      setSent(data.sent)
      onSent?.(data.sent)
    } catch (err) {
      setError(err.message || t('admin.notif_error'))
    } finally {
      setSending(false)
    }
  }

  const isBroadcast = userId === null
  const headerLabel = isBroadcast
    ? t('admin.notif_modal_title_broadcast')
    : t('admin.notif_modal_title_user').replace('{user}', username || String(userId))

  return (
    <div className="modal-backdrop" onClick={handleBackdrop}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h2 style={{ marginBottom: 16 }}>{headerLabel}</h2>

        {sent !== null ? (
          <div>
            <p style={{ color: 'var(--green)', marginBottom: 20 }}>
              {t('admin.notif_sent_ok').replace('{n}', sent)}
            </p>
            <div className="modal-actions">
              <button className="btn-primary" onClick={onClose}>{t('admin.notif_close')}</button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', marginBottom: 5, fontSize: '0.85rem' }}>
                {t('admin.notif_title_label')}
              </label>
              <input
                className="input"
                type="text"
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder={t('admin.notif_title_placeholder')}
                maxLength={200}
                disabled={sending}
                style={{ width: '100%' }}
              />
            </div>

            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', marginBottom: 5, fontSize: '0.85rem' }}>
                {t('admin.notif_body_label')}
              </label>
              <textarea
                className="input"
                rows={4}
                value={body}
                onChange={e => setBody(e.target.value)}
                placeholder={t('admin.notif_body_placeholder')}
                disabled={sending}
                style={{ width: '100%', resize: 'vertical' }}
              />
            </div>

            {error && (
              <p style={{ color: 'var(--red, #dc2626)', marginBottom: 12, fontSize: '0.85rem' }}>
                {error}
              </p>
            )}

            <div className="modal-actions">
              <button type="button" className="btn-ghost" onClick={onClose} disabled={sending}>
                {t('admin.cancel')}
              </button>
              <button
                type="submit"
                className="btn-primary"
                disabled={sending || !title.trim() || !body.trim()}
              >
                {sending ? t('admin.sending') : t('admin.notif_send_btn_submit')}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
