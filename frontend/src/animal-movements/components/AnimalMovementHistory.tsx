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
          <table className="expedient-records" role="table">
            <thead><tr><th scope="col">Fecha</th><th scope="col">Tipo</th><th scope="col">Origen</th><th scope="col">Destino</th><th scope="col">Motivo</th><th scope="col">Acciones</th></tr></thead>
            <tbody role="rowgroup">
              {[...history].sort((a, b) => b.date.localeCompare(a.date)).map((item) => (
                <tr role="row" key={item.id}>
                  <td data-label="Fecha" role="cell">{item.date.split('-').reverse().join('/')}</td>
                  <td data-label="Tipo" role="cell">{types.find((type) => type.id === item.movement_type_id)?.name ?? 'Tipo no disponible'}</td>
                  <td data-label="Origen" role="cell">{location(item.origin_farm_id, item.origin_lot_id, 'Sin origen')}</td>
                  <td data-label="Destino" role="cell">{location(item.destination_farm_id, item.destination_lot_id, 'Sin destino')}</td>
                  <td data-label="Motivo" role="cell">{item.reason?.trim() || '—'}</td>
                  <td data-label="Acciones" role="cell">
                    <button id={`repro-open-movement-${item.id}`} type="button" aria-controls="repro-panel-movement" onClick={() => onDetail(item.id)}>Ver detalles</button>
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
