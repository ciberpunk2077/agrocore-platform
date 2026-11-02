import RecordChart from './RecordChart'
import type { WeightHistory } from '../../weights/types'

export default function WeightOverview({ records }: { records: WeightHistory[] }) {
  const ordered = [...records].sort((a, b) => b.date.localeCompare(a.date))
  if (!ordered.length) return null
  const last = ordered[0]
  const uniqueLatest = ordered.length === 1 || ordered[1].date !== last.date
  return <div className="expedient-weight-overview">
    <div className="expedient-metric"><span>Último peso disponible</span>
      <strong>{uniqueLatest ? `${last.weight} kg` : 'Sin datos'}</strong>
      <p>{uniqueLatest ? last.date : 'Varios pesajes en la última fecha; consulta los registros sin asumir un orden.'}</p>
    </div>
    <RecordChart title="Evolución del peso" unit="kg" points={records.map(r => ({ date: r.date, value: r.weight }))} />
  </div>
}
