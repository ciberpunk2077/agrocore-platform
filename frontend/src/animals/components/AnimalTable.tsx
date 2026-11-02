import { Link } from 'react-router-dom'
import type { Animal } from '../types'
import { displayValue, identification } from '../inventory'
import { AnimalIdentity, AnimalStatusBadge } from './InventoryAnimal'

export default function AnimalTable({ animals }: { animals: Animal[] }) {
  return <div className="inventory-table-scroll" role="region" aria-label="Tabla de animales; desplazamiento horizontal disponible" tabIndex={0}>
    <table className="inventory-table"><caption>Inventario de animales · página actual</caption><thead><tr>
      {['Identificación', 'Especie', 'Raza', 'Sexo', 'Estado', 'Finca', 'Lote', 'Expediente'].map(label => <th scope="col" key={label}>{label}</th>)}
    </tr></thead><tbody>{animals.map(animal => <tr key={animal.id}>
      <th scope="row"><AnimalIdentity animal={animal} /></th>
      <td>{displayValue(animal.species)}</td><td>{displayValue(animal.breed)}</td><td>{displayValue(animal.gender)}</td>
      <td><AnimalStatusBadge animal={animal} /></td><td>{displayValue(animal.farm)}</td><td>{displayValue(animal.lot)}</td>
      <td><Link className="inventory-record-link" to={`/animals/${animal.id}`} aria-label={`Ver expediente de ${identification(animal)}`}>Ver expediente <span aria-hidden="true">→</span></Link></td>
    </tr>)}</tbody></table>
  </div>
}
