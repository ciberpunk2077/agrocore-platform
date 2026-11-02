import { useCallback, useEffect, useRef, useState } from 'react'
import { useCurrentContext } from '../auth/current-context'
import { useSession } from '../auth/useSession'
import { getSession, getSessionRevision, subscribeSession } from '../auth/session'
import { getDashboardSummary, getUpcomingBirths } from '../dashboard/dashboard.service'
import SummaryCard from '../dashboard/components/SummaryCard'
import AnimalDistribution from '../dashboard/components/AnimalDistribution'
import UpcomingBirthAgenda from '../dashboard/components/UpcomingBirthAgenda'
import DashboardIcon from '../dashboard/components/DashboardIcon'
import DashboardFollowUp from '../dashboard/components/DashboardFollowUp'
import type { DashboardSummary, UpcomingBirth } from '../dashboard/types'
import { normalizeApiError } from '../lib/api-errors'
import './DashboardPage.css'

export default function DashboardPage() {
  const context = useCurrentContext()
  const { session, revision } = useSession()
  if (!session || context.status !== 'loaded') return <p role="status">Cargando contexto del Dashboard...</p>
  if (!context.currentOrganization || !context.canRead) return <p role="alert">No tienes acceso al Dashboard de la organización.</p>
  // The provider retains the last server snapshot while renewing its lease.
  // Only a changed civil day creates a new scope; lease renewal is not a retry.
  const businessToday = context.data.business_time?.business_today ?? null
  return <DashboardScope key={`${revision}:${context.currentOrganization.id}:${businessToday}`}
    revision={revision} organizationId={context.currentOrganization.id} businessToday={businessToday}
    isCurrentOrganization={context.isCurrentOrganization} />
}

interface ScopeProps {
  revision: number
  organizationId: string
  businessToday: string | null
  isCurrentOrganization: (id: string) => boolean
}
type DashboardState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'loaded'; summary: DashboardSummary; upcomingBirths: UpcomingBirth[] }

export function DashboardScope({ revision, organizationId, businessToday, isCurrentOrganization }: ScopeProps) {
  const [state, setState] = useState<DashboardState>({ status: 'loading' })
  const alive = useRef(false), generation = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const load = useCallback(async () => {
    const session = getSession()
    if (!alive.current || !session || revision !== getSessionRevision() || !isCurrentOrganization(organizationId)) return
    controller.current?.abort()
    const c = new AbortController(), order = ++generation.current
    controller.current = c
    const current = () => alive.current && !c.signal.aborted && controller.current === c
      && generation.current === order && revision === getSessionRevision() && isCurrentOrganization(organizationId)
    try {
      const [summary, upcomingBirths] = await Promise.all([
        getDashboardSummary(session.access, c.signal), getUpcomingBirths(session.access, c.signal),
      ])
      if (current()) setState({ status: 'loaded', summary, upcomingBirths })
    } catch (cause) {
      if (current()) {
        setState({ status: 'error', message: normalizeApiError(cause, 'No fue posible cargar el Dashboard. Intenta de nuevo.').message })
        c.abort() // Cancel the other read; never publish a partial pair.
      }
    }
  }, [revision, organizationId, isCurrentOrganization])

  function refresh() {
    if (!alive.current || revision !== getSessionRevision() || !isCurrentOrganization(organizationId)) return
    setState({ status: 'loading' })
    void load()
  }

  useEffect(() => {
    let mounted = true
    alive.current = true
    const unsubscribe = subscribeSession(() => {
      generation.current++
      controller.current?.abort()
      setState({ status: 'loading' })
    })
    queueMicrotask(() => { if (mounted) void load() })
    return () => {
      mounted = false
      alive.current = false
      controller.current?.abort()
      unsubscribe()
    }
  }, [load])

  return <section className="dashboard-page ag-dashboard-theme" data-ag-theme="light" aria-busy={state.status === 'loading'}>
    <header className="dashboard-page__header">
      <div><span className="dashboard-page__eyebrow">AgroCore Platform</span><h1>Panel de control ganadero</h1>
      <p>Resumen integral de la operación</p>
      <p className="dashboard-page__business-date">{businessToday ? <>Fecha operativa del contexto: <time dateTime={businessToday}>{businessToday}</time></> : 'Fecha operativa no disponible.'}</p></div>
      <button className="ag-button ag-button--primary" type="button" onClick={refresh} disabled={state.status === 'loading'}><DashboardIcon name="refresh" />Actualizar</button>
    </header>
    {state.status === 'loading' ? <p className="ag-state ag-state--loading" role="status">Cargando Dashboard...</p>
      : state.status === 'error' ? <div>
        <p className="ag-state ag-state--error" role="alert">{state.message}</p>
        <button className="ag-button ag-button--secondary" type="button" onClick={refresh}>Reintentar</button>
      </div> : <>
        <div className="dashboard-summary">
          <SummaryCard icon="herd" label="Total de animales" value={state.summary.total_animals} />
          <SummaryCard icon="active" label="Animales activos" value={state.summary.active_animals} />
          <SummaryCard icon="pregnancy" label="Gestaciones" to="/dashboard/pregnancies" value={state.summary.pregnancies} />
          <SummaryCard icon="birth" label="Nacimientos este mes" to="/dashboard/births_this_month" value={state.summary.births_this_month} />
          <SummaryCard icon="calendar" label="Próximos nacimientos" to="/dashboard/upcoming_births" value={state.summary.upcoming_births} />
          <SummaryCard icon="vaccination" label="Vacunaciones pendientes" to="/dashboard/vaccinations_due" value={state.summary.vaccinations_due} />
          <SummaryCard icon="weight" label="Peso promedio" value={state.summary.average_weight !== null ? `${state.summary.average_weight} kg` : 'Sin datos'} />
        </div>
        <div className="dashboard-panels">
          <AnimalDistribution total={state.summary.total_animals} active={state.summary.active_animals} />
          <UpcomingBirthAgenda births={state.upcomingBirths} businessToday={businessToday} />
        </div>
        <DashboardFollowUp summary={state.summary} />
      </>}
  </section>
}
