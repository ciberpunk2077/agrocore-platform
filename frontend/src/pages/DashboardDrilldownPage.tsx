import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useCurrentContext } from '../auth/current-context'
import { useSession } from '../auth/useSession'
import { getSession, getSessionRevision } from '../auth/session'
import { businessTimeIsFresh } from '../auth/business-time'
import type { BusinessTimeLease } from '../auth/types'
import { Button, Card, ErrorState, LoadingState } from '../ui/components'
import { getDrilldown } from '../dashboard/drilldown.service'
import { indicators, isIndicator } from '../dashboard/drilldown'
import type { Indicator, DrillSnapshot } from '../dashboard/drilldown'
import DrilldownResults from '../dashboard/components/DrilldownResults'
import './DashboardDrilldownPage.css'

export default function DashboardDrilldownPage() {
  const { indicator } = useParams<{ indicator: string }>()
  const context = useCurrentContext(), { session, revision } = useSession()
  if (!isIndicator(indicator)) return <ErrorState>Indicador no disponible. <Link to="/dashboard">Volver al Dashboard</Link></ErrorState>
  if (!session || context.status !== 'loaded') return <LoadingState>Cargando contexto...</LoadingState>
  if (!context.currentOrganization || !context.canRead) return <ErrorState>No tienes acceso a estos registros.</ErrorState>
  const today = context.data.business_time?.business_today
  if (!today || !context.businessTimeReady || !context.businessTimeLease) return <Card><p role="status">La fecha operativa necesita actualizarse antes de consultar el indicador.</p><Button onClick={() => { void context.refreshCurrentContext().catch(() => {}) }}>Actualizar contexto</Button><Link to="/dashboard">Volver al Dashboard</Link></Card>
  return <DrilldownScope key={`${revision}:${context.currentOrganization.id}:${indicator}:${today}`} indicator={indicator} today={today}
    revision={revision} organizationId={context.currentOrganization.id} lease={context.businessTimeLease} isCurrentOrganization={context.isCurrentOrganization} />
}
interface Props { indicator: Indicator; today: string; revision: number; organizationId: string; lease: BusinessTimeLease; isCurrentOrganization: (id: string) => boolean }
type State = { status: 'loading' } | { status: 'error'; message: string } | { status: 'loaded'; data: DrillSnapshot }
export function DrilldownScope({ indicator, today, revision, organizationId, lease, isCurrentOrganization }: Props) {
  const [state, setState] = useState<State>({ status: 'loading' }), [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController(), session = getSession()
    const current = () => !controller.signal.aborted && revision === getSessionRevision() && isCurrentOrganization(organizationId)
    async function load() {
      if (!session || !current()) return
      try {
        if (!businessTimeIsFresh(lease)) throw new Error('La fecha operativa caducó. Actualiza el contexto antes de continuar.')
        const data = await getDrilldown(indicator, today, session.access, controller.signal)
        if (!current()) return
        if (!businessTimeIsFresh(lease)) throw new Error('La fecha operativa caducó durante la consulta. Actualiza el contexto.')
        setState({ status: 'loaded', data })
      } catch (cause) {
        if (current()) { setState({ status: 'error', message: cause instanceof Error ? cause.message : 'No fue posible consultar los registros.' }); controller.abort() }
      }
    }
    void load()
    return () => controller.abort()
  }, [indicator, today, revision, organizationId, lease, isCurrentOrganization, attempt])
  return <section className="dashboard-drilldown"><header><p>AgroCore · Detalle del indicador</p><h1>{indicators[indicator].title}</h1><p>Fecha operativa: <time dateTime={today}>{today}</time></p><Link to="/dashboard">← Volver al Dashboard</Link></header>
    <Card className="drill-definition"><p>{indicators[indicator].definition}</p><Button variant="secondary" onClick={() => { setState({ status: 'loading' }); setAttempt(v => v + 1) }} disabled={state.status === 'loading'}>Actualizar registros</Button></Card>
    {state.status === 'loading' ? <LoadingState>Cargando registros...</LoadingState> : state.status === 'error' ? <ErrorState>{state.message}<Button variant="secondary" onClick={() => { setState({ status: 'loading' }); setAttempt(v => v + 1) }}>Reintentar</Button></ErrorState> : state.data.limitation ? <Card><h2>Detalle no verificable</h2><p>KPI consultado: {state.data.expected} registros.</p><p role="status">{state.data.limitation}</p></Card> : <DrilldownResults rows={state.data.rows} expected={state.data.expected} mothers={indicator === 'births_this_month'} />}
  </section>
}
