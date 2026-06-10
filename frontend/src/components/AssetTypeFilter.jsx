import { useAppConfig } from '../context/AppContext'

// Orden canónico de los tipos de producto.
export const ASSET_TYPE_ORDER = ['stock', 'fund', 'etf', 'crypto']

/** ¿El item (con market_type) entra en la selección de tipos? [] = todos. */
export function matchesTypes(item, types) {
  if (!types || types.length === 0) return true
  return types.includes(item.market_type || 'stock')
}

/** Tipos presentes en una lista de items, en orden canónico. */
export function presentTypes(items) {
  const set = new Set((items || []).map(i => i.market_type || 'stock'))
  return ASSET_TYPE_ORDER.filter(t => set.has(t))
}

/**
 * Segmentador de chips por tipo de producto (selección exclusiva).
 *  value     : array de tipos seleccionados ([] = Todo, máximo 1 elemento)
 *  onChange  : (nextArray) => void
 *  available : tipos a mostrar (en orden canónico)
 *
 * "Todo" se activa cuando value está vacío. Pulsar un tipo activo vuelve a
 * "Todo"; pulsar un tipo distinto lo sustituye (comportamiento radio).
 */
export default function AssetTypeFilter({ value = [], available = [], onChange }) {
  const { t } = useAppConfig()

  // Con un solo tipo disponible no tiene sentido segmentar.
  if (available.length < 2) return null

  function toggle(type) {
    // Si ya está seleccionado, deseleccionar (volver a Todo).
    onChange(value.includes(type) ? [] : [type])
  }

  const isAll = value.length === 0

  return (
    <div className="seg-filter">
      <button
        type="button"
        className={`seg-chip ${isAll ? 'active' : ''}`}
        onClick={() => onChange([])}
      >
        {t('seg.all')}
      </button>
      {available.map(type => (
        <button
          key={type}
          type="button"
          className={`seg-chip ${!isAll && value.includes(type) ? 'active' : ''}`}
          onClick={() => toggle(type)}
        >
          {t(`seg.${type}`)}
        </button>
      ))}
    </div>
  )
}
