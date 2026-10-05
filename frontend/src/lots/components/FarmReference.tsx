import { Link } from 'react-router-dom'
import type { Farm } from '../../farms/types'

function FarmReference({ farmId, farms }: { farmId: string; farms: ReadonlyMap<string, Farm> }) {
  const farm = farms.get(farmId)
  return farm
    ? <Link to={`/farms/${farm.id}`}>{farm.code.trim() || '—'} · {farm.name.trim() || '—'}</Link>
    : <span>Finca no disponible · {farmId}</span>
}

export default FarmReference
