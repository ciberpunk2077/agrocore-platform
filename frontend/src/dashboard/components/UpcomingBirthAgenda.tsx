import { Card, EmptyState } from '../../ui/components'
import { Link } from 'react-router-dom'
import DashboardIcon from './DashboardIcon'
import type { UpcomingBirth } from '../types'
import { daysRemaining, remainingLabel } from '../presentation'

export default function UpcomingBirthAgenda({ births, businessToday }: { births: UpcomingBirth[]; businessToday: string | null }) {
  return <Card className="dashboard-upcoming" role="region" aria-labelledby="dashboard-upcoming-title">
    <h2 id="dashboard-upcoming-title"><DashboardIcon name="calendar" />Próximos nacimientos</h2>
    <p className="dashboard-panel__description">Comprende hoy y los siguientes 30 días, inclusive.</p>
    {births.length === 0 ? <EmptyState>No hay próximos nacimientos.</EmptyState> : <ul className="dashboard-agenda" aria-label="Agenda de nacimientos previstos">
      {births.map((birth, index) => <li className="dashboard-agenda__item" key={`${birth.animal_id}:${index}`}>
        <div className="dashboard-agenda__animal"><span>Animal</span><strong><Link to={`/animals/${encodeURIComponent(birth.animal_id)}`}>{birth.animal}</Link></strong></div>
        <div className="dashboard-agenda__date"><span>Fecha estimada</span><time dateTime={birth.expected_birth}>{birth.expected_birth}</time></div>
        <span className="dashboard-agenda__remaining">{remainingLabel(daysRemaining(birth.expected_birth, businessToday))}</span>
      </li>)}
    </ul>}
  </Card>
}
