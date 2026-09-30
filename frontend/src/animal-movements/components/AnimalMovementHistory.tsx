import type { Farm, Lot } from '../../animals/types'
import type { AnimalMovement, MovementType } from '../types'
import './AnimalMovementHistory.css'

interface AnimalMovementHistoryProps {
  history: AnimalMovement[]
  types: MovementType[]
  farms: Farm[]
  lots: Lot[]
}

function AnimalMovementHistory({ history, types, farms, lots }: AnimalMovementHistoryProps) {
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
            <thead><tr><th>Fecha</th><th>Tipo</th><th>Origen</th><th>Destino</th><th>Motivo</th></tr></thead>
            <tbody>
              {history.map((item) => (
                <tr key={item.id}>
                  <td>{item.date.split('-').reverse().join('/')}</td>
                  <td>{types.find((type) => type.id === item.movement_type_id)?.name ?? 'Tipo no disponible'}</td>
                  <td>{location(item.origin_farm_id, item.origin_lot_id, 'Sin origen')}</td>
                  <td>{location(item.destination_farm_id, item.destination_lot_id, 'Sin destino')}</td>
                  <td>{item.reason?.trim() || '—'}</td>
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
