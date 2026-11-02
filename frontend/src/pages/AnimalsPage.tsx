import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import WriteOnly from '../auth/WriteOnly'
import { useCurrentContext } from '../auth/current-context'
import { useSession } from '../auth/useSession'
import { getSession, getSessionRevision } from '../auth/session'
import { getAnimals } from '../animals/animals.service'
import { isInventory } from '../animals/inventory'
import AnimalInventory from '../animals/components/AnimalInventory'
import type { Animal } from '../animals/types'
import { getDashboardSummary } from '../dashboard/dashboard.service'
import type { DashboardSummary } from '../dashboard/types'
import { Button, Card, ErrorState, LoadingState } from '../ui/components'
import './AnimalsPage.css'

export default function AnimalsPage() {
  const context = useCurrentContext()
  const { session, revision } = useSession()
  if (!session || context.status !== 'loaded') return <LoadingState>Cargando contexto del inventario...</LoadingState>
  if (!context.canRead || !context.currentOrganization) return <ErrorState>No tienes acceso al inventario de la organización.</ErrorState>
  return <InventoryScope key={`${revision}:${context.currentOrganization.id}`} revision={revision}
    organizationId={context.currentOrganization.id} isCurrentOrganization={context.isCurrentOrganization} />
}

interface ScopeProps {
  revision: number
  organizationId: string
  isCurrentOrganization: (id: string) => boolean
}
export function InventoryScope({ revision, organizationId, isCurrentOrganization }: ScopeProps) {
  const [animals, setAnimals] = useState<Animal[] | null>(null)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [summaryError, setSummaryError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const current = () => !controller.signal.aborted && revision === getSessionRevision() && isCurrentOrganization(organizationId)
    const session = getSession()
    if (!session || !current()) return () => controller.abort()
    void getAnimals(session.access, controller.signal).then(data => {
      if (!current()) return
      if (!isInventory(data)) throw new Error('Invalid animal list')
      setAnimals(data)
    }).catch(() => { if (current()) setError('No fue posible cargar los animales. Intenta de nuevo.') })
    void getDashboardSummary(session.access, controller.signal).then(data => {
      if (current()) setSummary(data)
    }).catch(() => { if (current()) setSummaryError(true) })
    return () => controller.abort()
  }, [revision, organizationId, isCurrentOrganization, attempt])
  const retry = () => { setError(null); setSummaryError(false); setAnimals(null); setSummary(null); setAttempt(value => value + 1) }
  const lots = animals ? new Set(animals.map(animal => animal.lot_id).filter(Boolean)).size : null
  return <section className="animals-page">
    <header className="animals-page__header"><div><p className="inventory-eyebrow">AgroCore · Animales</p><h1>Inventario ganadero</h1><p>Gestión y consulta de animales</p></div>
      <WriteOnly><Link className="inventory-existing-create" to="/animals/new">Nuevo animal</Link></WriteOnly>
    </header>
    <div className="inventory-stats" aria-label="Indicadores del inventario">
      {[['Total de animales', summary?.total_animals, 'Resumen de la organización'], ['Animales activos', summary?.active_animals, 'Resumen de la organización'], ['Lotes con animales', lots, 'En el listado activo']].map(([label, value, source]) => <Card key={String(label)} className="inventory-stat"><span className="inventory-stat__label">{label}</span><strong>{value ?? (label === 'Lotes con animales' ? error ? 'No disponible' : 'Cargando…' : summaryError ? 'No disponible' : 'Cargando…')}</strong><small>{source}</small></Card>)}
    </div>
    {summaryError && <p className="inventory-notice" role="status">Los indicadores de la organización no están disponibles. El listado puede consultarse de forma independiente.</p>}
    <p className="inventory-notice">El listado incluye animales con registro activo, según la API actual. Los filtros se aplican a todo ese listado; los indicadores superiores no cambian al filtrar.</p>
    {error ? <ErrorState>{error}<Button variant="secondary" onClick={retry}>Reintentar carga</Button></ErrorState> : animals === null ? <LoadingState>Cargando animales...</LoadingState> : <AnimalInventory animals={animals} />}
  </section>
}
