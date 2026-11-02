import { useState } from 'react'
import { Button, Card, EmptyState, Field, Input, Select } from '../../ui/components'
import { emptyFilters, filterAnimals, filterKeys, filterOptions, pageSize } from '../inventory'
import type { FilterKey } from '../inventory'
import type { Animal } from '../types'
import AnimalTable from './AnimalTable'
import AnimalCards from './AnimalCards'

export default function AnimalInventory({ animals }: { animals: Animal[] }) {
  const [view, setView] = useState<'table' | 'cards'>('table')
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState({ ...emptyFilters })
  const [page, setPage] = useState(1)
  const filtered = filterAnimals(animals, query, filters)
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const currentPage = Math.min(page, pages)
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const labels: Record<FilterKey, string> = { status_id: 'Estado', gender_id: 'Sexo', species_id: 'Especie', farm_id: 'Finca', lot_id: 'Lote' }
  const changeFilter = (key: FilterKey, value: string) => { setFilters({ ...filters, [key]: value, ...(key === 'farm_id' ? { lot_id: '' } : {}) }); setPage(1) }
  return <>
    <Card className="inventory-filters"><h2>Encuentra un animal</h2>
      <Field id="inventory-search" label="Buscar por nombre, identificador o aretes">{attributes => <Input {...attributes} type="search" placeholder="Ej. Luna, AG-024 o número de arete" value={query} onChange={event => { setQuery(event.target.value); setPage(1) }} />}</Field>
      <div className="inventory-filter-grid">{filterKeys.map(key => <Field key={key} id={`inventory-${key}`} label={labels[key]}>{attributes => <Select {...attributes} value={filters[key]} onChange={event => changeFilter(key, event.target.value)}>
        <option value="">Todos</option>{filterOptions(key === 'lot_id' && filters.farm_id ? filterAnimals(animals, '', { ...emptyFilters, farm_id: filters.farm_id }) : animals, key).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
      </Select>}</Field>)}</div><Button variant="ghost" onClick={() => { setFilters({ ...emptyFilters }); setQuery(''); setPage(1) }}>Limpiar filtros</Button>
    </Card>
    <div className="inventory-toolbar"><p role="status" aria-live="polite">{filtered.length} resultados de {animals.length} animales del listado activo</p>
      <div className="inventory-view-switch" role="group" aria-label="Vista del inventario"><Button variant={view === 'table' ? 'primary' : 'secondary'} aria-pressed={view === 'table'} onClick={() => setView('table')}>Tabla</Button><Button variant={view === 'cards' ? 'primary' : 'secondary'} aria-pressed={view === 'cards'} onClick={() => setView('cards')}>Tarjetas</Button></div>
    </div>
    {animals.length === 0 ? <EmptyState>No hay animales registrados en el listado activo.</EmptyState> : filtered.length === 0 ? <EmptyState>No hay resultados para los filtros seleccionados. Prueba otra búsqueda o limpia los filtros.</EmptyState> : <>
      {view === 'table' ? <AnimalTable animals={visible} /> : <AnimalCards animals={visible} />}
      <nav className="inventory-pagination" aria-label="Paginación de animales"><p>Mostrando {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, filtered.length)} de {filtered.length} resultados · Página {currentPage} de {pages}</p><div>
        <Button variant="secondary" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Anterior</Button><Button variant="secondary" disabled={currentPage === pages} onClick={() => setPage(currentPage + 1)}>Siguiente</Button>
      </div></nav>
    </>}
  </>
}
