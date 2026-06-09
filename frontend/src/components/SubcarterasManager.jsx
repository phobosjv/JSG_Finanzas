/**
 * SubcarterasManager
 * ==================
 * Modal para crear, editar y gestionar subcarteras (agrupaciones personalizadas
 * de posiciones). Dos vistas: lista de subcarteras y editor de una subcartera
 * (dos columnas: todas las posiciones | posiciones en la subcartera).
 */

import { useState, useMemo, useCallback } from 'react'
import { api } from '../api/client'

// ---------------------------------------------------------------------------
// Helper interno: badge de tipo de activo
// ---------------------------------------------------------------------------
function TypeBadge({ marketType, t }) {
  const type = marketType || 'stock'
  return (
    <span className={`badge-asset ${type}`} style={{ flexShrink: 0 }}>
      {t(`badge.${type}`)}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Vista: formulario de creación de subcartera
// ---------------------------------------------------------------------------
function CreateForm({ onCreated, onCancel, t }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      const sc = await api.post('/subcarteras', { name: name.trim(), description: description.trim() || null })
      onCreated(sc)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-group">
        <label>{t('subcarteras.name')}</label>
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder={t('subcarteras.name_placeholder')}
          autoFocus
          required
        />
      </div>
      <div className="form-group">
        <label>{t('subcarteras.description')}</label>
        <input
          type="text"
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder={t('subcarteras.desc_placeholder')}
        />
      </div>
      <div className="modal-actions">
        <button type="button" className="btn-ghost btn-sm" onClick={onCancel}>
          {t('common.cancel')}
        </button>
        <button type="submit" className="btn-primary btn-sm" disabled={saving || !name.trim()}>
          {t('subcarteras.create')}
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Vista: editor de dos columnas para asignar posiciones a una subcartera
// ---------------------------------------------------------------------------
function PositionEditor({ subcartera, allPositions, onUpdated, onBack, t }) {
  const [positionIds, setPositionIds] = useState(new Set(subcartera.position_ids))
  const [selectedLeft, setSelectedLeft] = useState(null)   // position.id seleccionado en columna izquierda
  const [selectedRight, setSelectedRight] = useState(null)  // position.id seleccionado en columna derecha
  const [searchLeft, setSearchLeft] = useState('')

  const sortedAll = useMemo(() =>
    [...allPositions].sort((a, b) =>
      (a.yahoo_ticker || a.name || '').localeCompare(b.yahoo_ticker || b.name || '')
    ),
    [allPositions]
  )

  const available = useMemo(() =>
    sortedAll.filter(p => {
      if (positionIds.has(p.position_id)) return false
      if (!searchLeft.trim()) return true
      const q = searchLeft.toLowerCase()
      return (p.yahoo_ticker || '').toLowerCase().includes(q) ||
             (p.name || '').toLowerCase().includes(q)
    }),
    [sortedAll, positionIds, searchLeft]
  )

  const inSubcartera = useMemo(() =>
    sortedAll.filter(p => positionIds.has(p.position_id)),
    [sortedAll, positionIds]
  )

  const handleAdd = useCallback(async () => {
    if (selectedLeft === null) return
    await api.post(`/subcarteras/${subcartera.id}/positions/${selectedLeft}`)
    const next = new Set(positionIds)
    next.add(selectedLeft)
    setPositionIds(next)
    setSelectedLeft(null)
    onUpdated({ ...subcartera, position_ids: [...next] })
  }, [selectedLeft, positionIds, subcartera, onUpdated])

  const handleRemove = useCallback(async () => {
    if (selectedRight === null) return
    await api.delete(`/subcarteras/${subcartera.id}/positions/${selectedRight}`)
    const next = new Set(positionIds)
    next.delete(selectedRight)
    setPositionIds(next)
    setSelectedRight(null)
    onUpdated({ ...subcartera, position_ids: [...next] })
  }, [selectedRight, positionIds, subcartera, onUpdated])

  // selectedLeft y selectedRight almacenan position_id (número entero)

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <button className="btn-ghost btn-sm" onClick={onBack}>{t('subcarteras.back')}</button>
        <span style={{ marginLeft: 12, fontWeight: 600 }}>{subcartera.name}</span>
        {subcartera.description && (
          <span style={{ marginLeft: 8, color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            — {subcartera.description}
          </span>
        )}
      </div>

      <div className="sc-editor-cols">
        {/* Columna izquierda: posiciones disponibles */}
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: 6, color: 'var(--text-muted)' }}>
            {t('subcarteras.all_positions')}
          </div>
          <input
            type="search"
            value={searchLeft}
            onChange={e => setSearchLeft(e.target.value)}
            placeholder={t('markets.search_placeholder')}
            style={{ width: '100%', marginBottom: 6, boxSizing: 'border-box' }}
          />
          <div className="sc-editor-col">
            {available.length === 0
              ? <div style={{ padding: '10px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  {t('subcarteras.no_positions')}
                </div>
              : available.map(p => (
                  <div
                    key={p.position_id}
                    className={`sc-pos-row${selectedLeft === p.position_id ? ' selected' : ''}`}
                    onClick={() => setSelectedLeft(prev => prev === p.position_id ? null : p.position_id)}
                  >
                    <TypeBadge marketType={p.market_type} t={t} />
                    <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{p.yahoo_ticker}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.name}
                    </span>
                  </div>
                ))
            }
          </div>
        </div>

        {/* Botones centrales */}
        <div className="sc-editor-actions">
          <button
            className="btn-primary btn-sm"
            disabled={selectedLeft === null}
            onClick={handleAdd}
            title={t('subcarteras.add')}
          >
            →
          </button>
          <button
            className="btn-ghost btn-sm"
            disabled={selectedRight === null}
            onClick={handleRemove}
            title={t('subcarteras.remove')}
          >
            ←
          </button>
        </div>

        {/* Columna derecha: posiciones en la subcartera */}
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: 6, color: 'var(--text-muted)' }}>
            {t('subcarteras.in_portfolio')}
          </div>
          <div className="sc-editor-col" style={{ marginTop: 36 }}>
            {inSubcartera.length === 0
              ? <div style={{ padding: '10px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  —
                </div>
              : inSubcartera.map(p => (
                  <div
                    key={p.position_id}
                    className={`sc-pos-row${selectedRight === p.position_id ? ' selected' : ''}`}
                    onClick={() => setSelectedRight(prev => prev === p.position_id ? null : p.position_id)}
                  >
                    <TypeBadge marketType={p.market_type} t={t} />
                    <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{p.yahoo_ticker}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.82rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.name}
                    </span>
                  </div>
                ))
            }
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Vista: lista de subcarteras
// ---------------------------------------------------------------------------
function SubcarterasList({ subcarteras, onEdit, onDelete, onNew, t }) {
  const [confirmDelete, setConfirmDelete] = useState(null)

  function handleDelete(sc) {
    if (confirmDelete === sc.id) {
      onDelete(sc.id)
      setConfirmDelete(null)
    } else {
      setConfirmDelete(sc.id)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn-primary btn-sm" onClick={onNew}>
          + {t('subcarteras.new')}
        </button>
      </div>

      {subcarteras.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          {t('subcarteras.empty')}
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {subcarteras.map(sc => (
            <div
              key={sc.id}
              style={{
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600 }}>{sc.name}</div>
                {sc.description && (
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                    {sc.description}
                  </div>
                )}
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 2 }}>
                  {sc.position_ids.length} posición{sc.position_ids.length !== 1 ? 'es' : ''}
                </div>
              </div>
              <button className="btn-ghost btn-sm" onClick={() => onEdit(sc)}>
                {t('subcarteras.edit')}
              </button>
              {confirmDelete === sc.id ? (
                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>¿Confirmar?</span>
                  <button className="btn-danger btn-sm" onClick={() => handleDelete(sc)}>
                    {t('subcarteras.delete')}
                  </button>
                  <button className="btn-ghost btn-sm" onClick={() => setConfirmDelete(null)}>
                    {t('common.cancel')}
                  </button>
                </div>
              ) : (
                <button className="btn-ghost btn-sm" style={{ color: 'var(--red)' }} onClick={() => handleDelete(sc)}>
                  {t('subcarteras.delete')}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------
export default function SubcarterasManager({
  subcarteras,
  onSubcarterasChange,
  positions,     // posiciones abiertas del usuario
  closed,        // posiciones cerradas del usuario
  onClose,
  t,
}) {
  // Todos los hooks antes de cualquier return
  const [view, setView] = useState('list')       // 'list' | 'edit' | 'create'
  const [editing, setEditing] = useState(null)   // subcartera que se está editando

  const allPositions = useMemo(() => {
    const seen = new Set()
    const result = []
    for (const p of [...(positions || []), ...(closed || [])]) {
      if (!seen.has(p.position_id)) {
        seen.add(p.position_id)
        result.push(p)
      }
    }
    return result
  }, [positions, closed])

  const handleCreated = useCallback((sc) => {
    onSubcarterasChange(prev => [...prev, sc])
    setView('list')
  }, [onSubcarterasChange])

  const handleUpdated = useCallback((updated) => {
    onSubcarterasChange(prev => prev.map(s => s.id === updated.id ? updated : s))
    setEditing(updated)
  }, [onSubcarterasChange])

  const handleDelete = useCallback(async (sc_id) => {
    await api.delete(`/subcarteras/${sc_id}`)
    onSubcarterasChange(prev => prev.filter(s => s.id !== sc_id))
  }, [onSubcarterasChange])

  const handleEdit = useCallback((sc) => {
    setEditing(sc)
    setView('edit')
  }, [])

  return (
    <div className="modal-backdrop" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div
        className="modal"
        style={{ maxWidth: view === 'edit' ? 700 : 500, width: '100%', maxHeight: '90vh', overflow: 'auto' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0 }}>{t('subcarteras.manage')}</h2>
          <button className="btn-ghost btn-sm" onClick={onClose}>{t('common.close')}</button>
        </div>

        {view === 'list' && (
          <SubcarterasList
            subcarteras={subcarteras}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onNew={() => setView('create')}
            t={t}
          />
        )}

        {view === 'create' && (
          <CreateForm
            onCreated={handleCreated}
            onCancel={() => setView('list')}
            t={t}
          />
        )}

        {view === 'edit' && editing && (
          <PositionEditor
            subcartera={editing}
            allPositions={allPositions}
            onUpdated={handleUpdated}
            onBack={() => { setView('list'); setEditing(null) }}
            t={t}
          />
        )}
      </div>
    </div>
  )
}
