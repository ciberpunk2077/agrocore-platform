import { Link } from 'react-router-dom'

import type { Animal } from '../types'

interface AnimalTableProps {
  animals: Animal[]
}

function getAnimalIdentification(animal: Animal): string {
  return (
    animal.name?.trim() ||
    animal.internal_id?.trim() ||
    animal.official_tag?.trim() ||
    'Sin identificación'
  )
}

function AnimalTable({ animals }: AnimalTableProps) {
  return (
    <div className="animal-table-container">
      <table className="animal-table">
        <thead>
          <tr>
            <th>Identificación</th>
            <th>Especie</th>
            <th>Raza</th>
            <th>Sexo</th>
            <th>Estado</th>
            <th>Finca</th>
            <th>Lote</th>
          </tr>
        </thead>

        <tbody>
          {animals.map((animal) => (
            <tr key={animal.id}>
              <td>
                <Link to={`/animals/${animal.id}`}>
                    {getAnimalIdentification(animal)}
                </Link>
               </td>
              <td>{animal.species}</td>
              <td>{animal.breed}</td>
              <td>{animal.gender}</td>
              <td>{animal.status}</td>
              <td>{animal.farm?.trim() || '—'}</td>
              <td>{animal.lot?.trim() || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default AnimalTable