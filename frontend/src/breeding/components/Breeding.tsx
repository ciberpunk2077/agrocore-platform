import { useEffect, useRef, useState } from 'react'
import WriteOnly from '../../auth/WriteOnly'
import { useCurrentContext } from '../../auth/current-context'
import { getSession, getSessionRevision, subscribeSession } from '../../auth/session'
import { businessTimeIsFresh } from '../../auth/business-time'
import type { BusinessTimeLease, ResolvedCurrentContext } from '../../auth/types'
import type { Animal, Gender } from '../../animals/types'
import { normalizeApiError } from '../../lib/api-errors'
import { ApiError } from '../../lib/api'
import { createBreeding, getAnimalBreedingHistory, getBreedingEvent, getBreedingAnimal, getBreedingAnimals, getBreedingGenders, getBreedingTypes, uncertainCreate } from '../breeding.service'
import { abandonScope, attemptKey, beginPreparation, finishAttempt, getAttempt, setAttemptPhase, type CreatePhase } from '../create-protocol'
import { matchesPayload, normalizedPayload, payloadError } from '../validation'
import type { BreedingCreatePayload, BreedingDetailState, BreedingEvent, BreedingType } from '../types'
import BreedingForm from './BreedingForm'
import BreedingHistory from './BreedingHistory'

interface Props { animal: Animal }
export default function Breeding(props: Props) {
  const context = useCurrentContext()
  const [revision, setRevision] = useState(getSessionRevision)
  useEffect(() => subscribeSession(() => setRevision(getSessionRevision())), [])
  if (context.status !== 'loaded' || !context.currentOrganization) return <p role="status">Cargando contexto reproductivo...</p>
  return <BreedingScope key={`${revision}:${context.currentOrganization.id}:${props.animal.id}:${context.canWrite}`}
    {...props} revision={revision} organizationId={context.currentOrganization.id} canWrite={context.canWrite}
    businessTimeLease={context.businessTimeLease} refreshCurrentContext={context.refreshCurrentContext}
    isCurrentOrganization={context.isCurrentOrganization} />
}

interface ScopeProps extends Props {
  revision: number
  organizationId: string
  canWrite: boolean
  businessTimeLease: BusinessTimeLease | null
  refreshCurrentContext: () => Promise<ResolvedCurrentContext>
  isCurrentOrganization: (id: string) => boolean
}

export function BreedingScope({ animal, revision, organizationId, canWrite, businessTimeLease, refreshCurrentContext, isCurrentOrganization }: ScopeProps) {
  const animalId = animal.id
  const key = attemptKey(revision, organizationId, animalId)
  const [phase, setPhase] = useState<CreatePhase>(() => getAttempt(key)?.phase === 'pending' ? 'uncertain' : getAttempt(key)?.phase ?? 'idle')
  const [options, setOptions] = useState<{ types: BreedingType[]; animals: Animal[]; genders: Gender[]; animal: Animal } | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  const [optionsLoading, setOptionsLoading] = useState(true)
  const [optionsAttempt, setOptionsAttempt] = useState(0)
  const [history, setHistory] = useState<BreedingEvent[]>([])
  const [detail, setDetail] = useState<BreedingDetailState>({ status: 'idle' })
  const detailReads = useRef(0)
  const activeDetail = useRef<string | null>(null)
  const detailController = useRef<AbortController | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [historyAttempt, setHistoryAttempt] = useState(0)
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState(() => getAttempt(key)?.phase === 'confirmed')
  const [readRecovered, setReadRecovered] = useState(false)
  const [compatible, setCompatible] = useState(false)
  const [formVersion, setFormVersion] = useState(0)
  const alive = useRef(false)
  const busy = useRef(false)
  const reads = useRef(0)
  const writes = useRef(0)
  const formGeneration = useRef(0)
  const historyReady = useRef(false)
  const optionsReady = useRef(false)
  const controllers = useRef(new Set<AbortController>())
  const current = () => alive.current && getSessionRevision() === revision && isCurrentOrganization(organizationId)
  const controller = () => { const c = new AbortController(); controllers.current.add(c); return c }

  useEffect(() => {
    const activeControllers = controllers.current
    alive.current = true
    return () => {
      alive.current = false
      abandonScope(key)
      activeControllers.forEach(c => c.abort())
      activeControllers.clear()
    }
  }, [key])

  useEffect(() => {
    const c = controller()
    const order = ++reads.current
    historyReady.current = false
    async function load() {
      setLoadingHistory(true); setHistoryError(null)
      const session = getSession()
      if (!session || !current()) { if (current()) { setHistoryError('No hay una sesión activa.'); setLoadingHistory(false) }; return }
      try {
        const result = await getAnimalBreedingHistory(animalId, session.access, c.signal)
        if (current() && !c.signal.aborted && order === reads.current) {
          historyReady.current = true; setHistory(result)
        }
      } catch (cause) {
        if (current() && !c.signal.aborted && order === reads.current) setHistoryError(normalizeApiError(cause, 'No fue posible cargar el historial reproductivo.').message)
      } finally {
        if (current() && !c.signal.aborted && order === reads.current) setLoadingHistory(false)
        controllers.current.delete(c)
      }
    }
    void load()
    return () => c.abort()
    // Context/session/animal changes remount this scope.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyAttempt])

  useEffect(() => {
    const c = controller()
    optionsReady.current = false
    async function load() {
      setOptionsError(null); setOptionsLoading(true)
      const session = getSession()
      if (!session || !current()) { if (current()) { setOptionsError('No hay una sesión activa.'); setOptionsLoading(false) }; return }
      try {
        const [types, animals, genders, fresh] = await Promise.all([
          getBreedingTypes(session.access, c.signal), getBreedingAnimals(session.access, c.signal),
          getBreedingGenders(session.access, c.signal), getBreedingAnimal(animalId, session.access, c.signal),
        ])
        if (current() && !c.signal.aborted) {
          optionsReady.current = true; setOptions({ types, animals, genders, animal: fresh })
        }
      } catch (cause) {
        if (current() && !c.signal.aborted) setOptionsError(normalizeApiError(cause, 'No fue posible preparar los datos reproductivos y el Animal fresco.').message)
      } finally { if (current() && !c.signal.aborted) setOptionsLoading(false); controllers.current.delete(c); c.abort() }
    }
    void load()
    return () => c.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optionsAttempt])

  async function synchronize() {
    const session = getSession()
    if (!session || !current()) return
    const c = controller()
    const order = ++reads.current
    historyReady.current = false
    setSyncing(true); setSyncError(null); setReadRecovered(false)
    try {
      const [result, fresh] = await Promise.all([
        getAnimalBreedingHistory(animalId, session.access, c.signal), getBreedingAnimal(animalId, session.access, c.signal),
      ])
      if (!current() || c.signal.aborted || order !== reads.current) return
      const attempt = getAttempt(key)
      setHistory(result); historyReady.current = true; setHistoryError(null); setLoadingHistory(false)
      setOptions(previous => previous ? { ...previous, animal: fresh } : previous)
      setReadRecovered(true)
      setCompatible(Boolean(attempt && result.some(item => matchesPayload(item, attempt.payload))))
      if (attempt?.phase === 'confirmed') {
        finishAttempt(key); setPhase('idle'); formGeneration.current++; setFormVersion(formGeneration.current)
      }
      // Equivalent rows never establish authorship of an uncertain CREATE.
    } catch (cause) {
      if (current() && !c.signal.aborted && order === reads.current) setSyncError(normalizeApiError(cause, 'No fue posible sincronizar historial y Animal. Reintenta solamente la lectura.').message)
    } finally {
      if (current() && !c.signal.aborted && order === reads.current) { setSyncing(false); busy.current = false }
      controllers.current.delete(c); c.abort()
    }
  }

  async function create(data: BreedingCreatePayload): Promise<boolean> {
    if (!current() || !canWrite || formVersion !== formGeneration.current || busy.current || getAttempt(key) || !optionsReady.current || !historyReady.current) return false
    const payload = normalizedPayload(data)
    if (!businessTimeIsFresh(businessTimeLease)) return false
    const invalid = payloadError(payload, animalId, businessTimeLease!.snapshot.business_today)
    if (invalid) throw new Error(invalid)
    const session = getSession()
    const localRevision = ++writes.current
    if (!session || !beginPreparation(key, payload, localRevision)) return false
    busy.current = true; setPhase('preparing'); setConfirmed(false); setReadRecovered(false); setCompatible(false); setSyncError(null)
    const c = controller()
    const validAttempt = () => current() && !c.signal.aborted && localRevision === writes.current && getAttempt(key)?.localRevision === localRevision
    let sent = false
    try {
      const [fresh, types, genders, male, freshContext] = await Promise.all([
        getBreedingAnimal(animalId, session.access, c.signal), getBreedingTypes(session.access, c.signal),
        getBreedingGenders(session.access, c.signal),
        payload.male_id === null ? Promise.resolve(null) : getBreedingAnimal(payload.male_id, session.access, c.signal),
        refreshCurrentContext(),
      ])
      if (!validAttempt()) return false
      setOptions(previous => previous ? { ...previous, animal: fresh, types, genders } : previous)
      if (!fresh.is_active || fresh.gender_id !== genders.find(g => g.code === 'F')?.id) throw new Error('El registro está disponible solamente para hembras activas.')
      if (!types.some(type => type.id === payload.breeding_type_id)) throw new Error('El tipo de reproducción seleccionado ya no está disponible.')
      if (male && (!male.is_active || male.id === animalId || male.gender_id !== genders.find(g => g.code === 'M')?.id)) throw new Error('Selecciona un macho activo y válido, distinto de la hembra.')
      let temporalContext = freshContext
      if (!businessTimeIsFresh(temporalContext.businessTimeLease)) temporalContext = await refreshCurrentContext()
      if (!validAttempt()) return false
      if (temporalContext.organization?.id !== organizationId || !temporalContext.can_write) throw new Error('La organización o los permisos cambiaron durante la preparación.')
      if (!businessTimeIsFresh(temporalContext.businessTimeLease)) throw new Error('La fecha operativa de la organización no está disponible. Recupera el contexto e intenta de nuevo.')
      const dateError = payloadError(payload, animalId, temporalContext.businessTimeLease!.snapshot.business_today)
      if (dateError) throw new Error(dateError)
      setAttemptPhase(key, 'pending'); setPhase('pending'); sent = true
      const saved = await createBreeding(payload, session.access, c.signal)
      if (!validAttempt()) return false
      setAttemptPhase(key, 'confirmed'); setPhase('confirmed'); setConfirmed(true)
      setHistory(previous => [saved, ...previous.filter(item => item.id !== saved.id)])
    } catch (cause) {
      if (!validAttempt()) return false
      if (sent && uncertainCreate(cause)) {
        setAttemptPhase(key, 'uncertain'); setPhase('uncertain'); busy.current = false
        return false
      }
      finishAttempt(key); setPhase('idle'); busy.current = false
      throw cause
    } finally {
      controllers.current.delete(c)
      // Aborting POST cannot prove non-persistence. A live abort stays uncertain.
      if (current() && getAttempt(key)?.localRevision === localRevision && getAttempt(key)?.phase === 'pending') {
        setAttemptPhase(key, 'uncertain'); setPhase('uncertain'); busy.current = false
      } else if (current() && getAttempt(key)?.localRevision === localRevision && getAttempt(key)?.phase === 'preparing') {
        finishAttempt(key); setPhase('idle'); busy.current = false
      }
      c.abort()
    }
    if (current()) await synchronize()
    return current()
  }

  function recover() {
    if (!current() || busy.current || !getAttempt(key)) return
    busy.current = true
    void synchronize()
  }

  function closeDetail() {
    if (!current()) return
    detailReads.current++
    activeDetail.current = null
    detailController.current?.abort()
    if (detailController.current) controllers.current.delete(detailController.current)
    detailController.current = null
    setDetail({ status: 'idle' })
  }

  async function openDetail(eventId: string) {
    if (!current() || !history.some(item => item.id === eventId)) return
    const session = getSession()
    if (!session) return
    closeDetail()
    const c = controller(), order = ++detailReads.current
    activeDetail.current = eventId
    detailController.current = c
    setDetail({ status: 'loading', eventId })
    const valid = () => current() && !c.signal.aborted && order === detailReads.current && activeDetail.current === eventId
    try {
      const fresh = await getBreedingEvent(eventId, animalId, session.access, c.signal)
      if (valid()) setDetail({ status: 'success', eventId, record: fresh })
    } catch (cause) {
      if (valid()) setDetail({ status: 'error', eventId, message: cause instanceof ApiError && cause.status === 404
        ? 'El evento reproductivo ya no está disponible.'
        : normalizeApiError(cause, 'No fue posible cargar el detalle del evento reproductivo. Intenta de nuevo.').message })
    } finally {
      controllers.current.delete(c)
      if (detailController.current === c) detailController.current = null
      c.abort()
    }
  }
  const fresh = options?.animal
  const femaleId = options?.genders.find(g => g.code === 'F')?.id
  const maleId = options?.genders.find(g => g.code === 'M')?.id
  const males = options?.animals.filter(candidate => candidate.is_active && candidate.id !== animalId && candidate.gender_id === maleId) ?? []
  const timeReady = businessTimeIsFresh(businessTimeLease)
  const locked = !timeReady || phase !== 'idle' || syncing || loadingHistory || optionsLoading || Boolean(historyError) || Boolean(optionsError) || !options
  return <section className="breeding" aria-label="Reproducción">
    <h2>Reproducción</h2>
    {optionsError ? <div><p role="alert">{optionsError}</p><button type="button" disabled={phase !== 'idle' || syncing} onClick={() => { optionsReady.current = false; setOptionsLoading(true); setOptionsAttempt(v => v + 1) }}>Reintentar carga de datos</button></div>
      : !options ? <p role="status">Cargando datos de reproducción...</p> : canWrite && <WriteOnly>
        {fresh?.is_active && fresh.gender_id === femaleId ? <BreedingForm key={formVersion} animal={fresh} types={options.types} males={males} disabled={locked}
          businessToday={timeReady ? businessTimeLease!.snapshot.business_today : null} onCreate={create} />
          : <p>El registro de eventos reproductivos está disponible para hembras activas.</p>}
      </WriteOnly>}
    {canWrite && !timeReady && <div><p role="status">La fecha operativa no está disponible. Recupera el contexto para registrar un evento.</p>
      <button type="button" onClick={() => { void refreshCurrentContext().catch(() => {}) }}>Recuperar contexto</button></div>}
    {phase === 'preparing' && <p role="status">Comprobando Animal y relaciones frescas antes de guardar...</p>}
    {phase === 'pending' && <p role="status">Guardando evento reproductivo...</p>}
    {confirmed && <p className="breeding-form__success" role="status">El evento reproductivo ya fue guardado correctamente.{syncing || phase === 'confirmed' ? ' Sincroniza las lecturas antes de registrar otro evento.' : ''}</p>}
    {phase === 'uncertain' && <div><p role="alert">Resultado incierto. No se repetirá el POST. El registro sigue bloqueado; recupera solamente las lecturas.</p>
      {readRecovered && <p>{compatible ? 'El historial contiene un evento compatible, pero no demuestra autoría de este intento.' : 'Las lecturas se recuperaron, pero no demuestran el resultado de este intento.'} El resultado sigue incierto.</p>}
    </div>}
    {syncError && <p role="alert">{syncError}</p>}
    {(phase === 'uncertain' || phase === 'confirmed') && <button type="button" disabled={syncing} onClick={recover}>Recuperar lecturas</button>}
    {syncing && <p role="status">Sincronizando historial y Animal...</p>}
    {loadingHistory ? <p role="status">Cargando historial reproductivo...</p> : historyError ? <div><p role="alert">{historyError}</p>
      <button type="button" disabled={phase !== 'idle' || syncing} onClick={() => { historyReady.current = false; setHistoryAttempt(v => v + 1) }}>Actualizar historial</button></div>
      : <BreedingHistory history={history} types={options?.types ?? []} animals={options?.animals ?? []}
        detail={detail} onOpenDetail={openDetail} onCloseDetail={closeDetail} />}
  </section>
}
