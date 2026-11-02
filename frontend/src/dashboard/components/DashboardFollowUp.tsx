import { Link } from 'react-router-dom'
import { Card } from '../../ui/components'
import type { DashboardSummary } from '../types'
import DashboardIcon from './DashboardIcon'
import ShellIcon from '../../components/navigation/ShellIcon'

export default function DashboardFollowUp({ summary }: { summary: DashboardSummary }) {
  return <Card className="dashboard-follow-up" role="region" aria-labelledby="dashboard-follow-up-title">
    <div className="dashboard-follow-up__heading"><h2 id="dashboard-follow-up-title">Actividad y seguimiento</h2><p>Indicadores de seguimiento y acceso a tus inventarios.</p></div>
    <div className="dashboard-follow-up__metrics">
      <div><span className="dashboard-follow-up__icon"><DashboardIcon name="vaccination" /></span><div><span>Vacunaciones pendientes</span><strong>{summary.vaccinations_due}</strong><p>Revisa los registros de salud en el expediente de cada animal.</p></div></div>
      <div><span className="dashboard-follow-up__icon"><DashboardIcon name="calendar" /></span><div><span>Próximos nacimientos</span><strong>{summary.upcoming_births}</strong><p>Previstos para hoy y los próximos 30 días, inclusive.</p></div></div>
    </div>
    <nav className="dashboard-quick-links" aria-label="Accesos rápidos de consulta">
      {([{ path: '/animals', label: 'Animales', icon: 'animals', description: 'Consultar el inventario y los expedientes' },
        { path: '/farms', label: 'Fincas', icon: 'farms', description: 'Consultar tus unidades ganaderas' },
        { path: '/lots', label: 'Lotes', icon: 'lots', description: 'Consultar espacios y capacidades registradas' }] as const).map(item =>
        <Link key={item.path} to={item.path}><span className="dashboard-follow-up__icon"><ShellIcon name={item.icon} /></span><span><strong>{item.label}</strong><small>{item.description}</small></span><span aria-hidden="true">→</span></Link>)}
    </nav>
  </Card>
}
