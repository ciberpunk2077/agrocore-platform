import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import WriteOnly from '../auth/WriteOnly'
import { useCurrentContext } from '../auth/current-context'
import { useSession } from '../auth/useSession'
import { getSession, getSessionRevision } from '../auth/session'
import { getFarms } from '../farms/farms.service'
import type { Farm } from '../farms/types'
import { isFarmInventory } from '../farms/farm-inventory'
import FarmInventory from '../farms/components/FarmInventory'
import { getLots } from '../lots/lots.service'
import { isLots } from '../animal-movements/validation'
import { getDashboardSummary } from '../dashboard/dashboard.service'
import { normalizeApiError } from '../lib/api-errors'
import { Button, Card, ErrorState, LoadingState } from '../ui/components'
import '../farms/farms.css'
import './FarmsPage.css'

export default function FarmsPage() {
  const context = useCurrentContext()
  const { session, revision } = useSession()
  if (!session || context.status !== 'loaded') return <LoadingState>Cargando contexto de fincas...</LoadingState>
  if (!context.canRead || !context.currentOrganization) return <ErrorState>No tienes acceso a las fincas de la organización.</ErrorState>
  return <FarmScope key={`${revision}:${context.currentOrganization.id}`} revision={revision} organizationId={context.currentOrganization.id} isCurrentOrganization={context.isCurrentOrganization} />
}
interface Props { revision: number; organizationId: string; isCurrentOrganization: (id: string) => boolean }
export function FarmScope({ revision, organizationId, isCurrentOrganization }: Props) {
  const [farms, setFarms] = useState<Farm[] | null>(null)
  const [lotCount, setLotCount] = useState<number | null>(null)
  const [animalCount, setAnimalCount] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const current = () => !controller.signal.aborted && revision === getSessionRevision() && isCurrentOrganization(organizationId)
    const session = getSession()
    if (!session || !current()) return () => controller.abort()
    void getFarms(session.access, controller.signal).then(data => {
      if (!current()) return
      if (!isFarmInventory(data)) throw new Error('Respuesta inválida de fincas')
      setFarms(data)
    }).catch(cause => { if (current()) setError(normalizeApiError(cause, 'No fue posible cargar las fincas. Intenta de nuevo.').message) })
    void getLots(session.access, controller.signal).then(data => {
      if (current() && isLots(data, organizationId)) setLotCount(data.length)
    }).catch(() => { /* Optional indicator: unavailable data is omitted. */ })
    void getDashboardSummary(session.access, controller.signal).then(data => {
      if (current()) setAnimalCount(data.total_animals)
    }).catch(() => { /* Optional indicator: unavailable data is omitted. */ })
    return () => controller.abort()
  }, [revision, organizationId, isCurrentOrganization, attempt])
  const retry = () => { setFarms(null); setLotCount(null); setAnimalCount(null); setError(null); setAttempt(value => value + 1) }
  return <section className="farms-page farm-premium">
    <header className="farm-premium-header"><div><p className="farm-premium-eyebrow">AgroCore · Unidades ganaderas</p><h1>Mis fincas</h1><p>Administra y consulta tus unidades ganaderas</p></div>
      <nav aria-label="Acciones de fincas"><Link className="farm-premium-link" to="/lots">Ver todos los lotes</Link><WriteOnly><Link className="farm-premium-create" to="/farms/new">Nueva finca</Link></WriteOnly></nav>
    </header>
    {(farms !== null || lotCount !== null || animalCount !== null) && <div className="farm-premium-stats" aria-label="Indicadores de la organización">
      {farms !== null && <Card><span>Fincas disponibles</span><strong>{farms.length}</strong><small>Registros activos de la organización</small></Card>}
      {lotCount !== null && <Card><span>Lotes disponibles</span><strong>{lotCount}</strong><small>Registros activos de la organización</small></Card>}
      {animalCount !== null && <Card><span>Total de animales</span><strong>{animalCount}</strong><small>Resumen de la organización</small></Card>}
    </div>}
    {error ? <ErrorState>{error}<Button variant="secondary" onClick={retry}>Reintentar</Button></ErrorState> : farms === null ? <LoadingState>Cargando fincas...</LoadingState> : <FarmInventory farms={farms} />}
  </section>
}
