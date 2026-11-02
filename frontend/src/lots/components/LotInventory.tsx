import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, EmptyState, Field, Input, Select } from '../../ui/components'
import ShellIcon from '../../components/navigation/ShellIcon'
import { farmText } from '../../farms/farm-inventory'
import type { Farm } from '../../farms/types'
import { filterLots, totalCapacity } from '../lot-inventory'
import type { Lot } from '../types'
import FarmReference from './FarmReference'
import './LotInventory.css'

export default function LotInventory({ lots, farms, farm }: { lots: Lot[]; farms: ReadonlyMap<string, Farm>; farm?: Farm }) {
  const [view, setView] = useState<'cards' | 'table'>('cards')
  const [query, setQuery] = useState('')
  const [selectedFarm, setSelectedFarm] = useState('')
  // A farm scope is an immutable boundary, independent of user-controlled filters.
  const scoped = farm ? lots.filter(lot => lot.farm_id === farm.id) : lots
  const filtered = filterLots(scoped, query, selectedFarm)
  const farmIds = [...new Set(scoped.map(lot => lot.farm_id))]
  const capacity = totalCapacity(scoped)
  const link = (lot: Lot) => <Link className="lot-premium-link" to={`/lots/${lot.id}`} aria-label={`Ver lote ${farmText(lot.name)}`}>Ver lote <span aria-hidden="true">→</span></Link>
  return <div className="lot-premium">
    {farm && <p className="lot-premium-context">Lotes de {farmText(farm.name)} · Solo esta finca</p>}
    <div className="lot-premium-stats" aria-label={farm ? 'Indicadores de lotes de esta finca' : 'Indicadores de lotes de la organización'}>
      <Card><span>Total de lotes</span><strong>{scoped.length}</strong><small>Registros activos {farm ? 'de esta finca' : 'de la organización'}</small></Card>
      <Card><span>Fincas vinculadas</span><strong>{farmIds.length}</strong><small>Según los lotes del inventario</small></Card>
      {capacity !== null && <Card><span>Capacidad total registrada</span><strong>{capacity}</strong><small>Suma registrada · no es ocupación</small></Card>}
    </div>
    <p className="lot-premium-notice">La API no especifica la unidad de capacidad. Los indicadores corresponden al inventario activo {farm ? 'de esta finca' : 'de la organización'} y no cambian al filtrar.</p>
    <Card className="lot-premium-filters"><Field id="lot-inventory-search" label="Buscar por nombre o código">{attributes => <Input {...attributes} type="search" placeholder="Nombre o código del lote" value={query} onChange={event => setQuery(event.target.value)} />}</Field>
      {!farm && <Field id="lot-inventory-farm" label="Finca">{attributes => <Select {...attributes} value={selectedFarm} onChange={event => setSelectedFarm(event.target.value)}><option value="">Todas las fincas</option>{farmIds.map(id => <option key={id} value={id}>{farms.has(id) ? farmText(farms.get(id)?.name) : 'Finca con referencia registrada'}</option>)}</Select>}</Field>}
      <Button variant="ghost" onClick={() => { setQuery(''); setSelectedFarm('') }}>Limpiar filtros</Button>
    </Card>
    <div className="lot-premium-toolbar"><p role="status" aria-live="polite">{filtered.length} resultados de {scoped.length} lotes</p><div role="group" aria-label="Vista de lotes">
      <Button variant={view === 'cards' ? 'primary' : 'secondary'} aria-pressed={view === 'cards'} onClick={() => setView('cards')}>Tarjetas</Button>
      <Button variant={view === 'table' ? 'primary' : 'secondary'} aria-pressed={view === 'table'} onClick={() => setView('table')}>Tabla</Button>
    </div></div>
    {!scoped.length ? <EmptyState>{farm ? 'Esta finca todavía no tiene lotes.' : 'No hay lotes registrados.'}</EmptyState> : !filtered.length ? <EmptyState>No hay resultados para los filtros seleccionados.</EmptyState> : view === 'cards' ?
      <ul className="lot-premium-grid" aria-label="Tarjetas de lotes">{filtered.map(lot => <li key={lot.id}><Card className="lot-premium-card">
        <span className="lot-premium-icon"><ShellIcon name="lots" /></span><div><h3>{farmText(lot.name)}</h3><p className="lot-premium-code">Código: {farmText(lot.code)}</p></div>
        <dl><div><dt>Finca</dt><dd><FarmReference farmId={lot.farm_id} farms={farms} /></dd></div><div><dt>Capacidad registrada</dt><dd>{lot.capacity}</dd></div></dl>{link(lot)}
      </Card></li>)}</ul> :
      <div className="lot-premium-table-scroll" role="region" aria-label="Tabla de lotes; desplazamiento horizontal disponible" tabIndex={0}><table className="lot-premium-table"><caption>Lotes {farm ? 'de esta finca' : 'disponibles'}</caption><thead><tr>
        {['Código', 'Nombre', 'Finca', 'Capacidad registrada', 'Consulta'].map(label => <th key={label} scope="col">{label}</th>)}
      </tr></thead><tbody>{filtered.map(lot => <tr key={lot.id}><td>{farmText(lot.code)}</td><th scope="row"><Link to={`/lots/${lot.id}`}>{farmText(lot.name)}</Link></th><td><FarmReference farmId={lot.farm_id} farms={farms} /></td><td>{lot.capacity}</td><td>{link(lot)}</td></tr>)}</tbody></table></div>}
  </div>
}
