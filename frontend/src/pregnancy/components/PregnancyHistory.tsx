import WriteOnly from '../../auth/WriteOnly'
import type { PregnancyRecord, PregnancyDetailState } from '../types'
import { dateLabel, detailAction, pregnancyStatus, recordDetail, reference } from '../../reproduction/RecordDetail'
import './PregnancyHistory.css'

interface PregnancyHistoryProps {
  history: PregnancyRecord[]; eventLabels: Map<string,string>; disabled: boolean
  onAbort: (item: PregnancyRecord) => void; detail: PregnancyDetailState
  onOpenDetail: (id: string) => void; onCloseDetail: () => void
}
function PregnancyHistory({ history, eventLabels, disabled, onAbort, detail, onOpenDetail, onCloseDetail }: PregnancyHistoryProps) {
  const record = detail.status === 'success' ? detail.record : null
  return <section className="pregnancy-history">
    <h3>Historial de gestaciones</h3>
    {detail.status !== 'idle' && recordDetail({ kind: 'pregnancy', id: detail.pregnancyId, title: 'Gestación', date: record?.diagnosis_date,
      status: record ? pregnancyStatus(record.status) : undefined,
      loading: detail.status === 'loading' ? 'Cargando detalle de la gestación...' : undefined,
      error: detail.status === 'error' ? detail.message : undefined,
      fields: record ? [
        { label: 'Fecha de diagnóstico', value: dateLabel(record.diagnosis_date) },
        { label: 'Estado', value: pregnancyStatus(record.status) },
        { label: 'Confirmada', value: record.confirmed ? 'Sí' : 'No' },
        { label: 'Fecha estimada de parto', value: dateLabel(record.expected_birth) },
        { label: 'Evento reproductivo', value: reference('event',record.breeding_id,eventLabels.get(record.breeding_id),record.animal_id,true) },
      ] : [], notes: record?.notes, onClose: onCloseDetail, onRetry: () => onOpenDetail(detail.pregnancyId) })}
    {history.length === 0 ? <p>Todavía no hay gestaciones para este animal.</p> : <div className="pregnancy-history__table-wrapper">
      <table className="expedient-records" role="table"><thead><tr><th scope="col">Diagnóstico</th><th scope="col">Fecha estimada de parto</th><th scope="col">Evento reproductivo</th><th scope="col">Estado</th><th scope="col">Acciones</th></tr></thead>
        <tbody role="rowgroup">{[...history].sort((a,b) => b.diagnosis_date.localeCompare(a.diagnosis_date)).map(item => <tr role="row" key={item.id}>
          <td data-label="Diagnóstico" role="cell">{dateLabel(item.diagnosis_date)}</td>
          <td data-label="Fecha estimada de parto" role="cell">{dateLabel(item.expected_birth)}</td>
          <td data-label="Evento reproductivo" role="cell">{reference('event',item.breeding_id,eventLabels.get(item.breeding_id),item.animal_id)}</td>
          <td data-label="Estado" role="cell">{pregnancyStatus(item.status)}</td>
          <td data-label="Acciones" role="cell">{detailAction('pregnancy',item.id,detail.status !== 'idle' && detail.pregnancyId === item.id,onOpenDetail,onCloseDetail)}
            {item.status === 'ACTIVE' && <WriteOnly fallback=""><button type="button" disabled={disabled} onClick={() => onAbort(item)}>Registrar aborto</button></WriteOnly>}</td>
        </tr>)}</tbody>
      </table></div>}
  </section>
}
export default PregnancyHistory
