import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, EmptyState } from '../../ui/components'
import ShellIcon from '../../components/navigation/ShellIcon'
import { farmText } from '../farm-inventory'
import type { Farm } from '../types'

export default function FarmInventory({ farms }: { farms: Farm[] }) {
  const [view, setView] = useState<'cards' | 'table'>('cards')
  const link = (farm: Farm) => <Link className="farm-premium-link" to={`/farms/${farm.id}`} aria-label={`Ver finca ${farmText(farm.name)}`}>Ver finca <span aria-hidden="true">→</span></Link>
  return <>
    <div className="farm-premium-toolbar"><p>{farms.length} fincas disponibles</p><div role="group" aria-label="Vista de fincas">
      <Button variant={view === 'cards' ? 'primary' : 'secondary'} aria-pressed={view === 'cards'} onClick={() => setView('cards')}>Tarjetas</Button>
      <Button variant={view === 'table' ? 'primary' : 'secondary'} aria-pressed={view === 'table'} onClick={() => setView('table')}>Tabla</Button>
    </div></div>
    {!farms.length ? <EmptyState>No hay fincas registradas.</EmptyState> : view === 'cards' ?
      <ul className="farm-premium-grid" aria-label="Tarjetas de fincas">{farms.map(farm => <li key={farm.id}><Card className="farm-premium-card">
        <span className="farm-premium-icon"><ShellIcon name="farms" /></span><div className="farm-premium-identity"><h2>{farmText(farm.name)}</h2><p>Código: {farmText(farm.code)}</p></div>
        <dl><div><dt>Tipo de finca</dt><dd>{farmText(farm.farm_type)}</dd></div><div><dt>Ciudad</dt><dd>{farmText(farm.city)}</dd></div><div><dt>Estado</dt><dd>{farmText(farm.state)}</dd></div></dl>{link(farm)}
      </Card></li>)}</ul> :
      <div className="farm-premium-table-scroll" role="region" aria-label="Tabla de fincas; desplazamiento horizontal disponible" tabIndex={0}><table className="farm-premium-table"><caption>Fincas disponibles</caption><thead><tr>
        {['Código', 'Nombre', 'Tipo', 'Ciudad', 'Estado', 'Consulta'].map(label => <th key={label} scope="col">{label}</th>)}
      </tr></thead><tbody>{farms.map(farm => <tr key={farm.id}><td>{farmText(farm.code)}</td><th scope="row"><Link to={`/farms/${farm.id}`}>{farmText(farm.name)}</Link></th><td>{farmText(farm.farm_type)}</td><td>{farmText(farm.city)}</td><td>{farmText(farm.state)}</td><td>{link(farm)}</td></tr>)}</tbody></table></div>}
  </>
}
