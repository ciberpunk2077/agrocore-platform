import './BirthHistory.css'
import type { Animal, Gender } from '../../animals/types'
import type { BirthRecord, BirthDetailState } from '../types'
import { animalName, dateLabel, detailAction, recordDetail, reference } from '../../reproduction/RecordDetail'

interface BirthHistoryProps {
  history: BirthRecord[]; animals: Animal[]; genders: Gender[]; disabled: boolean; detail: BirthDetailState
  onOpenDetail: (birthId: string) => void; onCloseDetail: () => void
}
function BirthHistory({ history, animals, genders, detail, onOpenDetail, onCloseDetail }: BirthHistoryProps) {
  const animalNames = new Map(animals.map(animal => [animal.id,animalName(animal)]))
  const genderNames = new Map(genders.map(gender => [gender.id,gender.name]))
  const record = detail.status === 'success' ? detail.record : null
  const calf = (item: BirthRecord, secondary = false) => reference('animal',item.calf_id,item.calf_id ? animalNames.get(item.calf_id) : undefined,undefined,secondary)
  const sex = (item: BirthRecord, secondary = false) => reference('gender',item.calf_gender_id,item.calf_gender_id ? genderNames.get(item.calf_gender_id) : undefined,undefined,secondary)
  return <section className="birth-history">
    <h3>Historial de partos</h3>
    {detail.status !== 'idle' && recordDetail({ kind: 'birth', id: detail.birthId, title: 'Parto', date: record?.birth_date,
      status: record ? record.alive ? 'Viva' : 'No viva' : undefined,
      loading: detail.status === 'loading' ? 'Cargando detalle del parto...' : undefined,
      error: detail.status === 'error' ? detail.message : undefined,
      fields: record ? [
        { label: 'Fecha del parto', value: dateLabel(record.birth_date) },
        { label: 'Cría', value: calf(record,true) },
        { label: 'Sexo', value: sex(record,true) },
        { label: 'Peso al nacimiento', value: `${record.birth_weight} kg` },
        { label: 'Estado de la cría', value: record.alive ? 'Viva' : 'No viva' },
        { label: 'Distocia', value: record.dystocia ? 'Sí' : 'No' },
      ] : [], notes: record?.notes, onClose: onCloseDetail, onRetry: () => onOpenDetail(detail.birthId) })}
    {history.length === 0 ? <p>Este animal todav?a no tiene partos registrados.</p> :
      <div className="birth-history__list">{[...history].sort((a,b) => b.birth_date.localeCompare(a.birth_date)).map(birth => <article className="birth-history__item" key={birth.id}>
        <div className="birth-history__field"><strong>Fecha del parto</strong><span>{dateLabel(birth.birth_date)}</span></div>
        <div className="birth-history__field"><strong>Cría</strong><span>{calf(birth)}</span></div>
        <div className="birth-history__field"><strong>Sexo</strong><span>{sex(birth)}</span></div>
        <div className="birth-history__field"><strong>Peso</strong><span>{birth.birth_weight} kg</span></div>
        <div className="birth-history__field"><strong>Estado</strong><span>{birth.alive ? 'Viva' : 'No viva'}</span></div>
        {detailAction('birth',birth.id,detail.status !== 'idle' && detail.birthId === birth.id,onOpenDetail,onCloseDetail)}
      </article>)}</div>}
  </section>
}
export default BirthHistory
