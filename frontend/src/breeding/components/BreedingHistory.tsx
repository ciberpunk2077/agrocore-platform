import type { Animal } from '../../animals/types'
import type { BreedingDetailState, BreedingEvent, BreedingType } from '../types'
import { animalName, dateLabel, detailAction, recordDetail, reference, textLabel } from '../../reproduction/RecordDetail'
import './BreedingHistory.css'

interface BreedingHistoryProps {
  history: BreedingEvent[]; types: BreedingType[]; animals: Animal[]; detail: BreedingDetailState
  onOpenDetail: (eventId: string) => void; onCloseDetail: () => void
}

function BreedingHistory({ history, types, animals, detail, onOpenDetail, onCloseDetail }: BreedingHistoryProps) {
  const typeNames = new Map(types.map(type => [type.id, type.name]))
  const animalNames = new Map(animals.map(animal => [animal.id, animalName(animal)]))
  const record = detail.status === 'success' ? detail.record : null
  return <section className="breeding-history">
    <h3>Historial reproductivo</h3>
    {detail.status !== 'idle' && recordDetail({ kind: 'breeding', id: detail.eventId, title: 'Servicio reproductivo', date: record?.date,
      loading: detail.status === 'loading' ? 'Cargando detalle del evento reproductivo...' : undefined,
      error: detail.status === 'error' ? detail.message : undefined,
      fields: record ? [
        { label: 'Fecha del servicio', value: dateLabel(record.date) },
        { label: 'Tipo de reproducción', value: reference('type', record.breeding_type_id, typeNames.get(record.breeding_type_id), undefined, true) },
        { label: 'Macho', value: reference('animal', record.male_id, record.male_id ? animalNames.get(record.male_id) : undefined, undefined, true) },
        { label: 'Fecha estimada de parto', value: dateLabel(record.expected_birth) },
        { label: 'Técnico', value: textLabel(record.technician) },
      ] : [], notes: record?.notes, onClose: onCloseDetail, onRetry: () => onOpenDetail(detail.eventId) })}
    {history.length === 0 ? <p>Todavía no hay eventos reproductivos para este animal.</p> :
      <div className="breeding-history__table-wrapper"><table className="expedient-records" role="table">
        <thead><tr><th scope="col">Fecha</th><th scope="col">Tipo de reproducción</th><th scope="col">Macho</th><th scope="col">Fecha estimada de parto</th><th scope="col">Acciones</th></tr></thead>
        <tbody role="rowgroup">{[...history].sort((a,b) => b.date.localeCompare(a.date)).map(item => <tr role="row" key={item.id}>
          <td data-label="Fecha" role="cell">{dateLabel(item.date)}</td>
          <td data-label="Tipo de reproducción" role="cell">{reference('type', item.breeding_type_id, typeNames.get(item.breeding_type_id))}</td>
          <td data-label="Macho" role="cell">{reference('animal', item.male_id, item.male_id ? animalNames.get(item.male_id) : undefined)}</td>
          <td data-label="Fecha estimada de parto" role="cell">{dateLabel(item.expected_birth)}</td>
          <td data-label="Acciones" role="cell">{detailAction('breeding',item.id,detail.status !== 'idle' && detail.eventId === item.id,onOpenDetail,onCloseDetail)}</td>
        </tr>)}</tbody>
      </table></div>}
  </section>
}
export default BreedingHistory
