import { useState, useMemo } from 'react'

/**
 * Ordenación de tablas en cliente, con 3 estados por columna:
 *   1er clic → ascendente · 2º clic → descendente · 3er clic → orden por defecto.
 *
 * La ordenación NO se persiste: al recargar se vuelve al orden por defecto
 * (el que trae `items`). Los valores nulos/NaN van siempre al final.
 *
 * Uso:
 *   const { sorted, sortKey, sortDir, requestSort } = useSortableData(items)
 *   ...
 *   <SortableHead columns={cols} sortKey={sortKey} sortDir={sortDir} requestSort={requestSort} />
 *   {sorted.map(...)}
 */
export function useSortableData(items) {
  const [config, setConfig] = useState(null) // { key, accessor, dir } | null

  const sorted = useMemo(() => {
    if (!config?.accessor) return items
    const { accessor, dir } = config
    const s = dir === 'desc' ? -1 : 1
    return [...items].sort((a, b) => {
      const va = accessor(a)
      const vb = accessor(b)
      const aNull = va == null || (typeof va === 'number' && Number.isNaN(va))
      const bNull = vb == null || (typeof vb === 'number' && Number.isNaN(vb))
      if (aNull && bNull) return 0
      if (aNull) return 1          // nulos siempre al final, sin importar dir
      if (bNull) return -1
      if (typeof va === 'number' && typeof vb === 'number') return s * (va - vb)
      return s * String(va).localeCompare(String(vb), undefined, { numeric: true, sensitivity: 'base' })
    })
  }, [items, config])

  function requestSort(key, accessor) {
    setConfig(prev => {
      if (!prev || prev.key !== key) return { key, accessor, dir: 'asc' }
      if (prev.dir === 'asc') return { key, accessor, dir: 'desc' }
      return null // 3er clic → orden por defecto
    })
  }

  return { sorted, sortKey: config?.key ?? null, sortDir: config?.dir ?? null, requestSort }
}

/**
 * Cabecera de tabla ordenable. `columns` es un array de:
 *   { key, label, accessor?, className?, style? }
 * Si `accessor` es undefined, la columna no es ordenable (cabecera fija).
 */
export function SortableHead({ columns, sortKey, sortDir, requestSort }) {
  return (
    <thead>
      <tr>
        {columns.map(col => {
          if (!col.accessor) {
            return (
              <th key={col.key} className={col.className} style={col.style}>
                {col.label}
              </th>
            )
          }
          const active = sortKey === col.key
          const arrow = active ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''
          return (
            <th
              key={col.key}
              className={col.className}
              style={{ cursor: 'pointer', userSelect: 'none', ...(col.style || {}) }}
              onClick={() => requestSort(col.key, col.accessor)}
              title="Ordenar"
            >
              {col.label}
              <span style={{ color: 'var(--accent)', fontSize: '0.8em' }}>{arrow}</span>
            </th>
          )
        })}
      </tr>
    </thead>
  )
}
