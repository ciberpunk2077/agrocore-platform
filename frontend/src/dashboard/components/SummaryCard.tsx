import { Card } from '../../ui/components'
import DashboardIcon from './DashboardIcon'
import { Link } from 'react-router-dom'

interface SummaryCardProps {
  label: string
  value: string | number
  to?: string
  icon?: 'herd' | 'active' | 'pregnancy' | 'birth' | 'calendar' | 'vaccination' | 'weight'
}

function SummaryCard({ label, value, icon = 'herd', to }: SummaryCardProps) {
  const card = (
    <Card className="summary-card" role="group" aria-label={label}>
      <div className="summary-card__heading"><span className="summary-card__icon"><DashboardIcon name={icon} /></span><span className="summary-card__label">{label}</span></div>
      <strong className="summary-card__value">{value}</strong>
      {to && <span className="summary-card__open">Ver registros <span aria-hidden="true">→</span></span>}
    </Card>
  )
  return to ? <Link to={to} className="summary-card-link" aria-label={`${label}: ${value}. Ver registros`}>{card}</Link> : card
}

export default SummaryCard
