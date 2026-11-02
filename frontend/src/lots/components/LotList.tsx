import { useEffect, useState } from 'react'
import { useCurrentContext } from '../../auth/current-context'
import { useSession } from '../../auth/useSession'
import { getSession, getSessionRevision } from '../../auth/session'
import { getFarms } from '../../farms/farms.service'
import { isFarmInventory } from '../../farms/farm-inventory'
import type { Farm } from '../../farms/types'
import { normalizeApiError } from '../../lib/api-errors'
import { isLots } from '../../animal-movements/validation'
import { Button, ErrorState, LoadingState } from '../../ui/components'
import { getLots } from '../lots.service'
import type { Lot } from '../types'
import LotInventory from './LotInventory'
import '../lots.css'

export default function LotList({ farm }: { farm?: Farm }) {
  const context = useCurrentContext()
  const { session, revision } = useSession()
  if (!session || context.status !== 'loaded') return <LoadingState>Cargando contexto de lotes...</LoadingState>
  if (!context.canRead || !context.currentOrganization) return <ErrorState>No tienes acceso a los lotes de la organización.</ErrorState>
  return <LotListScope key={`${revision}:${context.currentOrganization.id}:${farm?.id ?? 'all'}`} farm={farm} revision={revision} organizationId={context.currentOrganization.id} isCurrentOrganization={context.isCurrentOrganization} />
}
interface Props { farm?: Farm; revision: number; organizationId: string; isCurrentOrganization: (id: string) => boolean }
export function LotListScope({ farm, revision, organizationId, isCurrentOrganization }: Props) {
  const [lots, setLots] = useState<Lot[] | null>(null)
  const [farms, setFarms] = useState<ReadonlyMap<string, Farm>>(new Map())
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const current = () => !controller.signal.aborted && revision === getSessionRevision() && isCurrentOrganization(organizationId)
    const session = getSession()
    if (!session || !current()) return () => controller.abort()
    async function load() {
      try {
        const [lotData, farmData] = await Promise.all([
          getLots(session!.access, controller.signal),
          farm ? Promise.resolve([farm]) : getFarms(session!.access, controller.signal),
        ])
        if (!current()) return
        if (!isLots(lotData, organizationId) || !isFarmInventory(farmData) || lotData.some(lot => !Number.isSafeInteger(lot.capacity) || lot.capacity < 0)) throw new Error('Respuesta inválida de lotes')
        setLots(farm ? lotData.filter(lot => lot.farm_id === farm.id) : lotData)
        setFarms(new Map(farmData.map(item => [item.id, item])))
      } catch (cause) {
        if (current()) setError(normalizeApiError(cause, 'No fue posible cargar los lotes. Intenta de nuevo.').message)
      }
    }
    void load()
    return () => controller.abort()
  }, [farm, revision, organizationId, isCurrentOrganization, attempt])
  if (error) return <ErrorState>{error}<Button variant="secondary" onClick={() => { setError(null); setLots(null); setAttempt(value => value + 1) }}>Reintentar</Button></ErrorState>
  if (lots === null) return <LoadingState>Cargando lotes...</LoadingState>
  return <LotInventory lots={lots} farms={farms} farm={farm} />
}
