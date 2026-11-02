import type { ReactNode } from 'react'
import type { Animal } from '../types'
import { animalAge, animalParentLabel } from '../animal-detail'
import DashboardIcon from '../../dashboard/components/DashboardIcon'
import './AnimalGeneralInformation.css'

type Field = [label: string, value: string]
const display = (value: string | null | undefined) => value?.trim() || 'Sin datos'

function InformationBlock({ title, description, icon, fields, className = '', children }: {
  title: string; description: string; icon: 'herd' | 'weight' | 'active' | 'pregnancy' | 'calendar'; fields: Field[]; className?: string; children?: ReactNode
}) {
  return <section className={`animal-overview__block ${className}`} aria-label={title}>
    <header className="animal-overview__block-heading"><span className="animal-overview__icon"><DashboardIcon name={icon} /></span>
      <div><h3>{title}</h3><p>{description}</p></div>
    </header>
    <div className="animal-overview__block-content">{children}
      <dl className="animal-overview__fields">{fields.map(([label, value]) => <div className="animal-overview__field" key={label}>
        <dt>{label}</dt><dd className={value === 'Sin datos' ? 'animal-overview__empty' : undefined}>{value}</dd>
      </div>)}</dl>
    </div>
  </section>
}

export default function AnimalGeneralInformation({ animal, businessToday, weight, weightStatus }: {
  animal: Animal; businessToday: string | null; weight: string | null; weightStatus: 'loading' | 'loaded' | 'error'
}) {
  // The existing Animal contract has no photo field; do not infer URLs or use stock photos.
  return <div className="animal-overview">
    <InformationBlock title="Identificación" description="Registro e identificadores del animal" icon="herd" className="animal-overview__identity" fields={[
      ['Nombre', display(animal.name)], ['ID interno', display(animal.internal_id)], ['Especie', display(animal.species)],
      ['Raza', display(animal.breed)], ['Estado', display(animal.status)], ['Arete oficial', display(animal.official_tag)], ['Arete electrónico', display(animal.electronic_tag)],
    ]}>
      <div className="animal-overview__illustration"><DashboardIcon name="herd" /><span>Representación ilustrativa</span></div>
    </InformationBlock>
    <InformationBlock title="Datos biológicos" description="Nacimiento y desarrollo" icon="weight" fields={[
      ['Sexo', display(animal.gender)], ['Nacimiento', display(animal.birth_date)], ['Edad', animalAge(animal.birth_date, businessToday)],
      ['Último peso', weightStatus === 'loading' ? 'Cargando...' : display(weight)], ['Peso al nacer', animal.birth_weight !== null ? `${animal.birth_weight} kg` : 'Sin datos'],
    ]} />
    <InformationBlock title="Ubicación" description="Asignación actual en el rancho" icon="active" fields={[
      ['Finca', display(animal.farm)], ['Lote', display(animal.lot)],
    ]} />
    <InformationBlock title="Filiación" description="Referencias de madre y padre" icon="pregnancy" fields={[
      ['Madre', animalParentLabel(animal.mother_id, animal.mother_reference)], ['Padre', animalParentLabel(animal.father_id, animal.father_reference)],
    ]} />
    <InformationBlock title="Observaciones" description="Información adicional del registro" icon="calendar" className="animal-overview__notes" fields={[
      ['Notas', display(animal.notes)],
    ]} />
  </div>
}
