import { chartPoints, type ChartPoint } from '../record-chart'

export default function RecordChart({ title, unit, points }: { title: string; unit: string; points: ChartPoint[] }) {
  const data = chartPoints(points)
  if (!data) return <p className="expedient-chart-note">Gráfica no disponible: se requieren al menos dos registros válidos con fechas distintas, sin empates.</p>
  const minDate = Date.parse(data[0].date), duration = Date.parse(data[data.length - 1].date) - minDate
  const max = Math.max(...data.map(p => Number(p.value))) || 1
  const coords = data.map(p => ({ ...p, x: 65 + (Date.parse(p.date) - minDate) / duration * 590, y: 185 - Number(p.value) / max * 145 }))
  return <figure className="expedient-chart">
    <figcaption>{title} <span>· {unit}</span></figcaption>
    <svg viewBox="0 0 710 235" role="img" aria-label={`${title}. Eje vertical: ${unit}. Fechas y valores en los registros inferiores.`}>
      <desc>{data.map(p => `${p.date}: ${p.value} ${unit}`).join('; ')}</desc>
      <path d="M65 35V185H655" fill="none" stroke="#a3bcb0" />
      <path d="M65 112H655M65 40H655" fill="none" stroke="#e3eee8" strokeDasharray="4 4" />
      <text x="55" y="189" textAnchor="end">0</text>
      <text x="55" y="44" textAnchor="end">{max}</text>
      <polyline points={coords.map(p => `${p.x},${p.y}`).join(' ')} fill="none" stroke="#047857" strokeWidth="3" />
      {coords.map(p => <circle key={p.date} cx={p.x} cy={p.y} r="4" fill="#047857"><title>{`${p.date}: ${p.value} ${unit}`}</title></circle>)}
      <text x="65" y="215">{new Date(data[0].date).toISOString().slice(0, 10)}</text><text x="655" y="215" textAnchor="end">{new Date(data[data.length - 1].date).toISOString().slice(0, 10)}</text>
    </svg>
    <p>Solo mediciones registradas; las líneas unen puntos y no representan datos intermedios.{data.some(p => p.date.includes('T')) ? ' Horas en UTC; consulta los registros para el detalle.' : ''}</p>
  </figure>
}
