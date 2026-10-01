import type { PregnancyRecord } from '../types'
import './PregnancyHistory.css'

interface PregnancyHistoryProps {
  history: PregnancyRecord[]
  eventLabels: Map<string, string>
  disabled: boolean
  onAbort: (item: PregnancyRecord) => void
}

const statusLabels: Record<string, string> = { ACTIVE: 'Activa', FINISHED: 'Finalizada', ABORTED: 'Abortada' }

function PregnancyHistory({ history, eventLabels, disabled, onAbort }: PregnancyHistoryProps) {
  return <section className="pregnancy-history">
    <h3>Historial de gestaciones</h3>
    {history.length === 0 ? <p>Todavía no hay gestaciones para este animal.</p> : <div className="pregnancy-history__table-wrapper">
      <table>
        <thead><tr>
          <th scope="col">Diagnóstico</th><th scope="col">Fecha estimada de parto</th>
          <th scope="col">Evento reproductivo</th><th scope="col">Estado</th><th scope="col">Acciones</th>
        </tr></thead>
        <tbody>{history.map((item) => <tr key={item.id}>
          <td>{item.diagnosis_date.split('-').reverse().join('/')}</td>
          <td>{item.expected_birth.split('-').reverse().join('/')}</td>
          <td>{eventLabels.get(item.breeding_id) ?? 'Evento reproductivo no disponible'}
            {item.notes?.trim() && <details><summary>Ver notas</summary><p>{item.notes}</p></details>}
          </td>
          <td>{statusLabels[item.status] ?? 'Estado no disponible'}</td>
          <td>{item.status === 'ACTIVE' ? <button type="button" disabled={disabled}
            onClick={() => onAbort(item)}>Registrar aborto</button> : '—'}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </section>
}

export default PregnancyHistory
