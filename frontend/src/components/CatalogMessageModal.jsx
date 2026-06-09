import { useState } from 'react'
import { useAppConfig } from '../context/AppContext'
import { api } from '../api/client'

/**
 * Modal simple para que un usuario normal envíe un mensaje libre al admin.
 *
 * Props:
 *   onClose()      — cierra el modal.
 *   onSubmitted()  — callback opcional tras enviar con éxito.
 */
export default function CatalogMessageModal({ onClose, onSubmitted }) {
  const { t } = useAppConfig()
  const [message, setMessage]     = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError]         = useState('')
  const [success, setSuccess]     = useState(false)

  function handleBackdrop(e) {
    if (e.target === e.currentTarget) onClose()
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!message.trim()) { setError(t('requests.message_required')); return }
    setError('')
    setSubmitting(true)
    try {
      await api.post('/catalog/messages', { message: message.trim() })
      setSuccess(true)
      onSubmitted?.()
    } catch (err) {
      setError(err.message || 'Error al enviar el mensaje')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={handleBackdrop}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 460 }}>
        <h2 style={{ marginBottom: 16 }}>{t('requests.contact_title')}</h2>

        {success ? (
          <div>
            <p style={{ color: 'var(--green)', marginBottom: 20 }}>{t('requests.message_success')}</p>
            <div className="modal-actions">
              <button className="btn-primary" onClick={onClose}>{t('requests.close')}</button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', marginBottom: 6, fontSize: '0.85rem' }}>
                {t('requests.message_label')}
              </label>
              <textarea
                className="input"
                rows={5}
                value={message}
                onChange={e => setMessage(e.target.value)}
                placeholder={t('requests.message_placeholder')}
                disabled={submitting}
                style={{ width: '100%', resize: 'vertical' }}
              />
            </div>

            {error && (
              <p style={{ color: 'var(--red, #dc2626)', marginBottom: 12, fontSize: '0.85rem' }}>
                {error}
              </p>
            )}

            <div className="modal-actions">
              <button type="button" className="btn-ghost" onClick={onClose} disabled={submitting}>
                {t('requests.cancel')}
              </button>
              <button type="submit" className="btn-primary" disabled={submitting || !message.trim()}>
                {submitting ? t('requests.sending') : t('requests.send_btn')}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
