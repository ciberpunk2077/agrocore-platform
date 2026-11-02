import { Link } from 'react-router-dom'
import { Card } from '../../ui/components'
import { displayValue, identification } from '../inventory'
import type { Animal } from '../types'
import { AnimalIdentity, AnimalStatusBadge } from './InventoryAnimal'

export default function AnimalCards({ animals }: { animals: Animal[] }) {
  return <ul className="inventory-grid" aria-label="Tarjetas de animales">{animals.map(animal => <li key={animal.id}><Card className="inventory-animal-card">
    <AnimalIdentity animal={animal} /><AnimalStatusBadge animal={animal} />
    <dl>{(['species', 'breed', 'gender', 'farm', 'lot'] as const).map((key, index) => <div key={key}><dt>{['Especie', 'Raza', 'Sexo', 'Finca', 'Lote'][index]}</dt><dd>{displayValue(animal[key])}</dd></div>)}</dl>
    <Link className="inventory-record-link" to={`/animals/${animal.id}`} aria-label={`Ver expediente de ${identification(animal)}`}>Ver expediente <span aria-hidden="true">→</span></Link>
  </Card></li>)}</ul>
}
