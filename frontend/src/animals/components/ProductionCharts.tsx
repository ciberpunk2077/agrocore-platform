import RecordChart from './RecordChart'
import type { ProductionRecord, ProductionType } from '../../production/types'

export default function ProductionCharts({ records, types }: { records: ProductionRecord[]; types: ProductionType[] }) {
  const groups = new Map<string, ProductionRecord[]>()
  for (const record of records) {
    if (!record.unit?.trim()) continue
    const key = JSON.stringify([record.production_type_id, record.unit])
    groups.set(key, [...(groups.get(key) ?? []), record])
  }
  return <div className="expedient-charts">{[...groups].map(([key, rows]) => <RecordChart key={key}
    title={types.find(t => t.id === rows[0].production_type_id)?.name ?? `Tipo ${rows[0].production_type_id}`}
    unit={rows[0].unit || 'Sin unidad registrada'} points={rows.map(r => ({ date: r.recorded_at, value: r.quantity }))} />)}</div>
}
