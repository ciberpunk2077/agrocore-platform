import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getSession } from '../../auth/session'
import { getFarms } from '../../farms/farms.service'
import type { Farm } from '../../farms/types'
import { normalizeApiError } from '../../lib/api-errors'
import { getLots } from '../lots.service'
import type { Lot } from '../types'
import FarmReference from './FarmReference'
import '../lots.css'

function LotList({ farm }: { farm?: Farm }) {
  const [attempt, setAttempt] = useState(0)
  return <LotListData key={`${farm?.id ?? 'all'}-${attempt}`} farm={farm} onRetry={() => setAttempt((value) => value + 1)} />
}

function LotListData({ farm, onRetry }: { farm?: Farm; onRetry: () => void }) {
  const [lots, setLots] = useState<Lot[]>([])
  const [farms, setFarms] = useState<ReadonlyMap<string, Farm>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    async function load() {
      try {
        const session = getSession()
        if (!session) throw new Error('No hay sesión activa.')
        const [lotData, farmData] = await Promise.all([
          getLots(session.access),
          farm ? Promise.resolve([farm]) : getFarms(session.access),
        ])
        if (active) {
          setLots(farm ? lotData.filter((lot) => lot.farm_id === farm.id) : lotData)
          setFarms(new Map(farmData.map((item) => [item.id, item])))
        }
      } catch (cause) {
        if (active) setError(normalizeApiError(cause, 'No fue posible cargar los lotes. Intenta de nuevo.').message)
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => { active = false }
  }, [farm])

  if (loading) return <p role="status">Cargando lotes...</p>
  if (error) return <div><p role="alert">{error}</p><button type="button" onClick={onRetry}>Reintentar</button></div>
  if (!lots.length) return <p>{farm ? 'Esta finca todavía no tiene lotes.' : 'No hay lotes registrados.'}</p>
  return (
    <div className="lots-table-wrapper">
      <table className="lots-table">
        <caption>Lotes {farm ? 'de esta finca' : 'disponibles'}</caption>
        <thead><tr><th scope="col">Código</th><th scope="col">Nombre</th>{!farm && <th scope="col">Finca</th>}<th scope="col">Capacidad</th></tr></thead>
        <tbody>{lots.map((lot) => <tr key={lot.id}>
          <td>{lot.code.trim() || '—'}</td>
          <td><Link to={`/lots/${lot.id}`}>{lot.name.trim() || '—'}</Link></td>
          {!farm && <td><FarmReference farmId={lot.farm_id} farms={farms} /></td>}
          <td>{lot.capacity}</td>
        </tr>)}</tbody>
      </table>
    </div>
  )
}

export default LotList
