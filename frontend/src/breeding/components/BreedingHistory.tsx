import type { Animal } from '../../animals/types'
import { animalLabel } from '../breeding.service'
import type { BreedingEvent, BreedingType } from '../types'
import './BreedingHistory.css'

interface BreedingHistoryProps {
  history: BreedingEvent[]
  types: BreedingType[]
  animals: Animal[]
}

function formatDate(date: string) {
  return date.split('-').reverse().join('/')
}

function BreedingHistory({ history, types, animals }: BreedingHistoryProps) {
  const typeNames = new Map(types.map((type) => [type.id, type.name]))
  const animalNames = new Map(animals.map((animal) => [animal.id, animalLabel(animal)]))
  return (
    <section className="breeding-history">
      <h3>Historial reproductivo</h3>
      {history.length === 0 ? <p>Todavía no hay eventos reproductivos para este animal.</p> : (
        <div className="breeding-history__table-wrapper">
          <table>
            <thead><tr>
              <th scope="col">Fecha</th><th scope="col">Tipo de reproducción</th>
              <th scope="col">Macho</th><th scope="col">Fecha estimada de parto</th>
            </tr></thead>
            <tbody>{history.map((item) => <tr key={item.id}>
              <td>{formatDate(item.date)}</td>
              <td>{typeNames.get(item.breeding_type_id) ?? item.breeding_type_id}
                {(item.technician?.trim() || item.notes?.trim()) && <details>
                  <summary>Ver detalles</summary>
                  <dl>
                    {item.technician?.trim() && <div><dt>Técnico</dt><dd>{item.technician}</dd></div>}
                    {item.notes?.trim() && <div><dt>Notas</dt><dd>{item.notes}</dd></div>}
                  </dl>
                </details>}
              </td>
              <td>{item.male_id ? animalNames.get(item.male_id) ?? item.male_id : '—'}</td>
              <td>{item.expected_birth ? formatDate(item.expected_birth) : '—'}</td>
            </tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default BreedingHistory
