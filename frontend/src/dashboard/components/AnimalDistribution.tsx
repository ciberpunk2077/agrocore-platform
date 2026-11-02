import { Card, EmptyState } from '../../ui/components'
import { animalDistribution, percentLabel } from '../presentation'

export default function AnimalDistribution({ total, active }: { total: number; active: number }) {
  const distribution = animalDistribution(total, active)
  return <Card className="dashboard-distribution" role="region" aria-labelledby="dashboard-distribution-title">
    <h2 id="dashboard-distribution-title">Distribución de animales</h2>
    <p className="dashboard-panel__description">Composición del total de animales por estado.</p>
    {!distribution ? <p>No es posible representar la distribución con estos conteos.</p> : <>
      {total === 0 ? <EmptyState>No hay animales para representar.</EmptyState> : <div className="dashboard-distribution__chart" aria-hidden="true">
        <svg viewBox="0 0 120 120" className="dashboard-distribution__donut" focusable="false">
          <circle cx="60" cy="60" r="46" className="dashboard-distribution__track" />
          <circle cx="60" cy="60" r="46" pathLength="100" className="dashboard-distribution__segment" strokeDasharray={`${distribution.activePercent} 100`} transform="rotate(-90 60 60)" />
          <text x="60" y="59" textAnchor="middle" className="dashboard-distribution__percentage">{percentLabel(distribution.activePercent)}</text>
          <text x="60" y="73" textAnchor="middle" className="dashboard-distribution__caption">activos</text>
        </svg>
      </div>}
      <dl className="dashboard-distribution__legend">
        <div><dt><span className="dashboard-distribution__swatch dashboard-distribution__active" aria-hidden="true" />Activos</dt><dd><strong>{distribution.active}</strong><span>{percentLabel(distribution.activePercent)}</span></dd></div>
        <div><dt><span className="dashboard-distribution__swatch dashboard-distribution__other" aria-hidden="true" />Otros estados</dt><dd><strong>{distribution.other}</strong><span>{percentLabel(distribution.otherPercent)}</span></dd></div>
      </dl>
      <p className="dashboard-panel__description">Total: {total} animales. Otros estados = total menos activos. Porcentajes redondeados a un decimal.</p>
    </>}
  </Card>
}
