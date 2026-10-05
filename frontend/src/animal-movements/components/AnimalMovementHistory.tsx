import type { Farm, Lot } from '../../animals/types'
import type { AnimalMovement, MovementType } from '../types'
import './AnimalMovementHistory.css'

interface AnimalMovementHistoryProps {
  history: AnimalMovement[]
  types: MovementType[]
  farms: Farm[]
  lots: Lot[]
  onDetail: (id: string) => void
  onEdit?: (id: string) => void
  onDelete?: (id: string) => void
  editDisabled: boolean
  deleteDisabled?: boolean
}

function AnimalMovementHistory({ history, types, farms, lots, onDetail, onEdit, onDelete, editDisabled, deleteDisabled = editDisabled }: AnimalMovementHistoryProps) {
  function location(farmId: string | null, lotId: string | null, empty: string) {
    if (!farmId && !lotId) return empty
    const farm = farms.find((item) => item.id === farmId)?.name ?? 'Finca no disponible'
    const lot = lots.find((item) => item.id === lotId)?.name ?? 'Lote no disponible'
    return lotId ? `${farm} / ${lot}` : farm
  }

  return (
    <section className="movement-history">
      <h3>Historial de movimientos</h3>
      {history.length === 0 ? <p>Todavía no hay movimientos para este animal.</p> : (
        <div className="movement-history__table-wrapper">
          <table>
            <thead><tr><th>Fecha</th><th>Tipo</th><th>Origen</th><th>Destino</th><th>Motivo</th><th>Acciones</th></tr></thead>
            <tbody>
              {history.map((item) => (
                <tr key={item.id}>
                  <td>{item.date.split('-').reverse().join('/')}</td>
                  <td>{types.find((type) => type.id === item.movement_type_id)?.name ?? 'Tipo no disponible'}</td>
                  <td>{location(item.origin_farm_id, item.origin_lot_id, 'Sin origen')}</td>
                  <td>{location(item.destination_farm_id, item.destination_lot_id, 'Sin destino')}</td>
                  <td>{item.reason?.trim() || '—'}</td>
                  <td>
                    <button type="button" onClick={() => onDetail(item.id)}>Ver detalles</button>
                    {onEdit && <button type="button" disabled={editDisabled || item.id !== history[0]?.id} onClick={() => onEdit(item.id)}>Editar</button>}
                    {onDelete && <button type="button" disabled={deleteDisabled || item.id !== history[0]?.id} onClick={() => onDelete(item.id)}>Eliminar</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default AnimalMovementHistory
