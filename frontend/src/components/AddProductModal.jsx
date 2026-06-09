import { useState, useEffect } from 'react'
import { useAppConfig } from '../context/AppContext'
import { api } from '../api/client'

/**
 * Modal para que un usuario normal solicite la agregación de un producto
 * al catálogo de inversión.
 *
 * Props:
 *   defaultMarket  — código de mercado pre-seleccionado (el que estaba activo).
 *   onClose()      — cierra el modal.
 *   onSubmitted()  — callback opcional tras enviar con éxito.
 */
export default function AddProductModal({ defaultMarket, onClose, onSubmitted }) {
  const { t } = useAppConfig()

  const [ticker, setTicker]     = useState('')
  const [isin, setIsin]         = useState('')
  const [name, setName]         = useState('')
  const [marketId, setMarketId] = useState(defaultMarket || '')
  const [markets, setMarkets]   = useState([])
  const [preview, setPreview]   = useState(null)   // null | {name, currency, exchange, last_price, in_catalog}
  const [validating, setValidating] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError]       = useState('')
  const [success, setSuccess]   = useState(false)

  // Cargar lista de mercados al abrir
  useEffect(() => {
    api.get('/markets/list')
      .then(data => setMarkets(data || []))
      .catch(() => {})
  }, [])

  function handleBackdrop(e) {
    if (e.target === e.currentTarget) onClose()
  }

  async function handleValidate() {
    const t_ticker = ticker.trim().toUpperCase()
    if (!t_ticker) { setError(t('requests.ticker_required')); return }
    setError('')
    setPreview(null)
    setValidating(true)
    try {
      const data = await api.get(`/catalog/validate-ticker?ticker=${encodeURIComponent(t_ticker)}`)
      setPreview(data)
      // Auto-rellenar nombre si está vacío
      if (!name.trim() && data.name) setName(data.name)
    } catch (err) {
      setError(err.message || 'Error al validar el ticker')
    } finally {
      setValidating(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!preview) { setError(t('requests.validate_first')); return }
    if (!name.trim()) { setError(t('requests.name_required')); return }
    if (!marketId) { setError(t('requests.market_required')); return }
    setError('')
    setSubmitting(true)
    try {
      await api.post('/catalog/requests', {
        ticker: ticker.trim().toUpperCase(),
        isin: isin.trim() || null,
        name: name.trim(),
        market_id: marketId,
        currency: preview.currency || null,
      })
      setSuccess(true)
      onSubmitted?.()
    } catch (err) {
      setError(err.message || 'Error al enviar la solicitud')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={handleBackdrop}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
        <h2 style={{ marginBottom: 16 }}>{t('requests.modal_title')}</h2>

        {success ? (
          <div>
            <p style={{ color: 'var(--green)', marginBottom: 20 }}>{t('requests.success')}</p>
            <div className="modal-actions">
              <button className="btn-primary" onClick={onClose}>{t('requests.close')}</button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            {/* Ticker + Botón Validar */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: '0.85rem' }}>
                  {t('requests.ticker_label')} *
                </label>
                <input
                  className="input"
                  value={ticker}
                  onChange={e => { setTicker(e.target.value.toUpperCase()); setPreview(null) }}
                  placeholder={t('requests.ticker_placeholder')}
                  disabled={validating || submitting}
                  style={{ width: '100%' }}
                />
              </div>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleValidate}
                disabled={validating || submitting || !ticker.trim()}
                style={{ whiteSpace: 'nowrap' }}
              >
                {validating ? t('requests.validating') : t('requests.validate_btn')}
              </button>
            </div>

            {/* Preview resultado de validación */}
            {preview && (
              <div style={{
                background: 'var(--surface-2, #f4f4f5)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                padding: '10px 14px',
                marginBottom: 14,
                fontSize: '0.85rem',
              }}>
                <strong style={{ display: 'block', marginBottom: 6 }}>{t('requests.preview_title')}</strong>
                {preview.in_catalog && (
                  <p style={{ color: 'var(--orange, #d97706)', marginBottom: 4 }}>
                    ⚠ {t('requests.in_catalog')}
                  </p>
                )}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px' }}>
                  {preview.last_price != null && (
                    <>
                      <span style={{ color: 'var(--text-muted)' }}>{t('requests.preview_price')}:</span>
                      <span>{preview.last_price?.toLocaleString()}</span>
                    </>
                  )}
                  {preview.currency && (
                    <>
                      <span style={{ color: 'var(--text-muted)' }}>{t('requests.preview_currency')}:</span>
                      <span>{preview.currency}</span>
                    </>
                  )}
                  {preview.exchange && (
                    <>
                      <span style={{ color: 'var(--text-muted)' }}>{t('requests.preview_exchange')}:</span>
                      <span>{preview.exchange}</span>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* ISIN */}
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: '0.85rem' }}>
                {t('requests.isin_label')}
              </label>
              <input
                className="input"
                value={isin}
                onChange={e => setIsin(e.target.value.toUpperCase())}
                placeholder={t('requests.isin_placeholder')}
                disabled={submitting}
                style={{ width: '100%' }}
              />
            </div>

            {/* Nombre */}
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: '0.85rem' }}>
                {t('requests.name_label')} *
              </label>
              <input
                className="input"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder={t('requests.name_placeholder')}
                disabled={submitting}
                style={{ width: '100%' }}
              />
            </div>

            {/* Mercado */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: '0.85rem' }}>
                {t('requests.market_label')} *
              </label>
              <select
                className="input"
                value={marketId}
                onChange={e => setMarketId(e.target.value)}
                disabled={submitting}
                style={{ width: '100%' }}
              >
                <option value="">— {t('requests.market_required')} —</option>
                {markets.map(m => (
                  <option key={m.code} value={m.code}>{m.name}</option>
                ))}
              </select>
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
              <button
                type="submit"
                className="btn-primary"
                disabled={submitting || !preview || preview.in_catalog}
              >
                {submitting ? t('requests.submitting') : t('requests.submit_btn')}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
