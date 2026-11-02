import { Children, isValidElement, type ReactNode } from 'react'
import type { Animal } from '../../types'

const paths = {
  pencil: 'm15 4 5 5M4 20l5-1L21 7l-5-5L4 14zM4 14l5 5',
  animal: 'M6 8 3 5v6l3 2M18 8l3-3v6l-3 2M6 8h12v10l-3 3H9l-3-3zM9 14h.01M15 14h.01M10 18h4',
  biology: 'M7 3c0 8 10 10 10 18M17 3c0 8-10 10-10 18M7 3h10M7 21h10M9 7h6M9 17h6M10 12h4',
  tag: 'M3 3h9l9 9-9 9-9-9zM7 7h.01',
  location: 'M12 22S4 14 4 9a8 8 0 1 1 16 0c0 5-8 13-8 13ZM15 9a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  family: 'M8 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM16 10a3 3 0 1 0 0-6M2 21v-4a6 6 0 0 1 12 0v4M16 14a5 5 0 0 1 6 5v2',
  notes: 'M5 2h10l4 4v16H5zM14 2v5h5M9 11h6M9 15h6M9 19h4',
  status: 'M2 12h5l3-8 4 16 3-8h5',
  system: 'M4 4h16v16H4zM8 8h8M8 12h8M8 16h4',
  lock: 'M6 10h12v11H6zM9 10V7a3 3 0 0 1 6 0v3M12 14v3',
} as const

export function PreviewIcon({ name }: { name: keyof typeof paths }) {
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}

export default function AnimalPreviewFields({ animal, organizationName, children }: { animal: Animal; organizationName?: string; children: ReactNode }) {
  const fields = Children.toArray(children).flatMap(node => {
    if (!isValidElement<{ children?: ReactNode }>(node)) return []
    // The form passes its existing field elements, rather than recreating their controls.
    if (node.type === 'div') return [node]
    return Children.toArray(node.props.children).filter(child => isValidElement(child) && child.type === 'div')
  })
  const control = (id: string) => fields.find(node => isValidElement<{ children?: ReactNode }>(node) && Children.toArray(node.props.children).some(label => isValidElement<{ htmlFor?: string }>(label) && label.props.htmlFor === id))
  const groups = [
    { title: 'Identificación', description: 'Datos básicos e identificadores del animal.', icon: 'animal', ids: ['internalId', 'name', 'officialTag', 'electronicTag'] },
    { title: 'Características biológicas', description: 'Sexo, nacimiento y peso registrado.', icon: 'biology', ids: ['gender', 'birthDate', 'birthWeight'] },
    { title: 'Clasificación', description: 'Especie, raza y estado registrados.', icon: 'tag', ids: ['species', 'breed', 'status'] },
    { title: 'Ubicación y relaciones', description: 'Ubicación actual y referencias de los progenitores.', icon: 'family', ids: ['farm', 'lot', 'mother', 'father'] },
    { title: 'Observaciones', description: 'Información adicional.', icon: 'notes', ids: ['notes'] },
  ] as const
  const display = (value?: string | null) => value?.trim() || 'Sin datos'
  return <div className="animal-preview-layout">
    <div className="animal-preview-layout__main">{groups.map(group => <section className="animal-preview-card" aria-label={group.title} key={group.title}>
      <header><span className="animal-preview-icon"><PreviewIcon name={group.icon} /></span><div><h2>{group.title}</h2><p>{group.description}</p></div></header>
      <div className={`animal-preview-card__fields${group.ids.length === 1 ? ' animal-preview-card__fields--wide' : ''}`}>{group.ids.map(id => control(id))}</div>
    </section>)}</div>
    <aside className="animal-preview-layout__aside" aria-label="Resumen del animal">
      <section className="animal-preview-card"><header><span className="animal-preview-icon"><PreviewIcon name="animal" /></span><h2>Fotografía</h2></header>
        <div className="animal-preview-photo"><span><PreviewIcon name="animal" /></span><strong>Sin fotografía</strong><p>El registro actual no proporciona una fotografía del animal.</p></div>
      </section>
      <section className="animal-preview-card animal-preview-state"><span className="animal-preview-icon"><PreviewIcon name="status" /></span><div><h2>Estado actual</h2><strong>{display(animal.status)}</strong><p>{animal.is_active ? 'Registro activo en la organización.' : 'Registro inactivo en la organización.'}</p></div></section>
      <section className="animal-preview-card animal-preview-location"><header><span className="animal-preview-icon"><PreviewIcon name="location" /></span><h2>Ubicación actual</h2></header><dl><div><dt>Finca</dt><dd>{display(animal.farm)}</dd></div><div><dt>Lote</dt><dd>{display(animal.lot)}</dd></div></dl></section>
      {organizationName && <section className="animal-preview-card"><header><span className="animal-preview-icon"><PreviewIcon name="system" /></span><h2>Información del sistema</h2></header><dl><div><dt>Organización</dt><dd>{organizationName}</dd></div></dl></section>}
    </aside>
  </div>
}
