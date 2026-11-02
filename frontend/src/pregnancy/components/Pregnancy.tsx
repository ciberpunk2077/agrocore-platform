import { useEffect, useRef, useState } from 'react'
import WriteOnly from '../../auth/WriteOnly'
import { useCurrentContext } from '../../auth/current-context'
import { getSession, getSessionRevision, subscribeSession } from '../../auth/session'
import { businessTimeIsFresh } from '../../auth/business-time'
import type { BusinessTimeLease, ResolvedCurrentContext } from '../../auth/types'
import type { Animal, Gender } from '../../animals/types'
import type { BreedingEvent, BreedingType } from '../../breeding/types'
import { getAnimalBreedingHistory, getBreedingAnimal, getBreedingAnimals, getBreedingGenders, getBreedingTypes } from '../../breeding/breeding.service'
import { normalizeApiError } from '../../lib/api-errors'
import { ApiError } from '../../lib/api'
import { abortPregnancy, createPregnancy, getAnimalPregnancyHistory, getPregnancyDetail, pregnancyErrorMessage, uncertainCreate } from '../pregnancy.service'
import { abandonScope, attemptKey, beginPreparation, finishAttempt, getAttempt, setAttemptPhase, type CreatePhase } from '../create-protocol'
import { abandonAbort, beginAbort, finishAbort, getAbortAttempt, prepareAbort, setAbortPhase, type AbortPhase } from '../abort-protocol'
import { matchesPayload, normalizedPayload, payloadError } from '../validation'
import type { PregnancyCreatePayload, PregnancyRecord, PregnancyDetailState } from '../types'
import PregnancyForm from './PregnancyForm'
import PregnancyHistory from './PregnancyHistory'

export default function Pregnancy({ animal, refreshVersion = 0 }: { animal: Animal; refreshVersion?: number }) {
  const context = useCurrentContext()
  const [revision, setRevision] = useState(getSessionRevision)
  useEffect(() => subscribeSession(() => setRevision(getSessionRevision())), [])
  if (context.status !== 'loaded' || !context.currentOrganization) return <p role="status">Cargando contexto de gestación...</p>
  return <PregnancyScope key={`${revision}:${context.currentOrganization.id}:${animal.id}:${context.canWrite}`}
    animal={animal} revision={revision} organizationId={context.currentOrganization.id} canWrite={context.canWrite} refreshVersion={refreshVersion}
    businessTimeLease={context.businessTimeLease} refreshCurrentContext={context.refreshCurrentContext}
    isCurrentOrganization={context.isCurrentOrganization} />
}
interface ScopeProps {
  refreshVersion?: number
  animal: Animal; revision: number; organizationId: string; canWrite: boolean
  businessTimeLease: BusinessTimeLease | null
  refreshCurrentContext: () => Promise<ResolvedCurrentContext>
  isCurrentOrganization: (id: string) => boolean
}
interface Options { events: BreedingEvent[]; types: BreedingType[]; animals: Animal[]; genders: Gender[]; animal: Animal }

export function PregnancyScope({ animal, revision, organizationId, canWrite, businessTimeLease, refreshCurrentContext, isCurrentOrganization, refreshVersion = 0 }: ScopeProps) {
  const animalId = animal.id, key = attemptKey(revision, organizationId, animalId)
  const [phase, setPhase] = useState<CreatePhase>(() => getAttempt(key)?.phase === 'pending' ? 'uncertain' : getAttempt(key)?.phase ?? 'idle')
  const [history, setHistory] = useState<PregnancyRecord[]>([])
  const [detail, setDetail] = useState<PregnancyDetailState>({ status: 'idle' })
  const detailReads = useRef(0)
  const activeDetail = useRef<string | null>(null)
  const detailController = useRef<AbortController | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyAttempt, setHistoryAttempt] = useState(0)
  const [options, setOptions] = useState<Options | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  const [optionsLoading, setOptionsLoading] = useState(canWrite)
  const [optionsAttempt, setOptionsAttempt] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const [confirmed, setConfirmed] = useState(() => getAttempt(key)?.phase === 'confirmed')
  const [abortSuccess, setAbortSuccess] = useState(() => getAbortAttempt(key)?.phase === 'confirmed')
  const [abortPhase, setAbortState] = useState<AbortPhase>(() => getAbortAttempt(key)?.phase === 'pending' ? 'uncertain' : getAbortAttempt(key)?.phase ?? 'idle')
  const [abortError, setAbortError] = useState<string | null>(null)
  const [abortObserved, setAbortObserved] = useState<string | null>(null)
  const [abortSyncing, setAbortSyncing] = useState(false)
  const writePermission = useRef(canWrite)
  useEffect(() => { writePermission.current = canWrite }, [canWrite])
  const [syncError, setSyncError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const abortBusy = abortPhase === 'preparing' || abortPhase === 'pending' || abortSyncing
  const [readRecovered, setReadRecovered] = useState(false)
  const [compatible, setCompatible] = useState(false)
  const [formVersion, setFormVersion] = useState(0)
  const alive = useRef(false), busy = useRef(false)
  const reads = useRef(0), optionReads = useRef(0), writes = useRef(0), formGeneration = useRef(0)
  const historyReady = useRef(false), optionsReady = useRef(false)
  const controllers = useRef(new Set<AbortController>())
  const current = () => alive.current && getSessionRevision() === revision && isCurrentOrganization(organizationId)
  const controller = () => { const c = new AbortController(); controllers.current.add(c); return c }
  useEffect(() => {
    const activeControllers = controllers.current
    alive.current = true
    return () => { alive.current = false; abandonScope(key); abandonAbort(key); activeControllers.forEach(c => c.abort()); activeControllers.clear() }
  }, [key])
  useEffect(() => {
    const c = controller(), order = ++reads.current
    historyReady.current = false
    async function load() {
      setHistoryLoading(true); setHistoryError(null)
      const session = getSession()
      if (!session || !current()) return
      try {
        const result = await getAnimalPregnancyHistory(animalId, session.access, c.signal)
        if (current() && !c.signal.aborted && order === reads.current) { setHistory(result); historyReady.current = true }
      } catch (cause) {
        if (current() && !c.signal.aborted && order === reads.current) setHistoryError(pregnancyErrorMessage(cause, 'No fue posible cargar el historial de gestaciones.'))
      } finally {
        if (current() && !c.signal.aborted && order === reads.current) setHistoryLoading(false)
        controllers.current.delete(c)
      }
    }
    void load()
    return () => c.abort()
    // Scope changes remount; results also verify revision, tenant and generation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyAttempt, refreshVersion])
  useEffect(() => {
    if (!canWrite) return
    const c = controller(), order = ++optionReads.current
    optionsReady.current = false
    async function load() {
      setOptionsLoading(true); setOptionsError(null)
      const session = getSession()
      if (!session || !current()) return
      try {
        const [events, types, animals, genders, fresh] = await Promise.all([
          getAnimalBreedingHistory(animalId, session.access, c.signal), getBreedingTypes(session.access, c.signal),
          getBreedingAnimals(session.access, c.signal), getBreedingGenders(session.access, c.signal), getBreedingAnimal(animalId, session.access, c.signal),
        ])
        if (current() && !c.signal.aborted && order === optionReads.current) { setOptions({ events, types, animals, genders, animal: fresh }); optionsReady.current = true }
      } catch (cause) {
        if (current() && !c.signal.aborted && order === optionReads.current) setOptionsError(pregnancyErrorMessage(cause, 'No fue posible cargar las opciones de gestación.'))
      } finally {
        if (current() && !c.signal.aborted && order === optionReads.current) setOptionsLoading(false)
        controllers.current.delete(c)
      }
    }
    void load()
    return () => c.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optionsAttempt, refreshVersion])
  async function synchronize() {
    const session = getSession()
    if (!session || !current()) return
    const c = controller(), order = ++reads.current
    historyReady.current = false
    setSyncing(true); setSyncError(null); setReadRecovered(false)
    try {
      const result = await getAnimalPregnancyHistory(animalId, session.access, c.signal)
      if (!current() || c.signal.aborted || order !== reads.current) return
      setHistory(result); setHistoryError(null); setHistoryLoading(false)
      const events = await getAnimalBreedingHistory(animalId, session.access, c.signal)
      if (!current() || c.signal.aborted || order !== reads.current) return
      historyReady.current = true
      setOptions(previous => previous ? { ...previous, events } : previous)
      setReadRecovered(true)
      const attempt = getAttempt(key)
      setCompatible(Boolean(attempt && result.some(p => matchesPayload(p, attempt.payload))))
      if (attempt?.phase === 'confirmed') { finishAttempt(key); setPhase('idle'); formGeneration.current++; setFormVersion(formGeneration.current) }
      return true
    } catch (cause) {
      if (current() && !c.signal.aborted && order === reads.current) setSyncError(pregnancyErrorMessage(cause, 'No fue posible sincronizar. Reintenta solamente las lecturas.'))
      return false
    } finally {
      if (current() && !c.signal.aborted && order === reads.current) { setSyncing(false); busy.current = false }
      controllers.current.delete(c); c.abort()
    }
  }
  async function create(data: PregnancyCreatePayload): Promise<boolean> {
    if (!current() || !canWrite || formVersion !== formGeneration.current || busy.current || getAbortAttempt(key) || getAttempt(key)
      || !historyReady.current || !optionsReady.current || !businessTimeIsFresh(businessTimeLease)) return false
    const payload = Object.freeze(normalizedPayload(data))
    const invalid = payloadError(payload, animalId, businessTimeLease!.snapshot.business_today, options?.events.find(e => e.id === payload.breeding_id)?.date)
    if (invalid) throw new Error(invalid)
    const session = getSession(), localRevision = ++writes.current
    if (!session || !beginPreparation(key, payload, localRevision)) return false
    busy.current = true; setPhase('preparing'); setConfirmed(false); setError(null); setFieldErrors({}); setSyncError(null); setReadRecovered(false)
    const c = controller()
    const validAttempt = () => current() && !c.signal.aborted && localRevision === writes.current && getAttempt(key)?.localRevision === localRevision
    let sent = false
    try {
      const [freshHistory, events, fresh, genders, context] = await Promise.all([
        getAnimalPregnancyHistory(animalId, session.access, c.signal), getAnimalBreedingHistory(animalId, session.access, c.signal),
        getBreedingAnimal(animalId, session.access, c.signal), getBreedingGenders(session.access, c.signal), refreshCurrentContext(),
      ])
      if (!validAttempt()) return false
      const selected = events.find(e => e.id === payload.breeding_id)
      if (!fresh.is_active || fresh.gender_id !== genders.find(g => g.code === 'F')?.id) throw new Error('El registro está disponible solamente para hembras activas.')
      if (!selected) throw new Error('El evento reproductivo seleccionado ya no está disponible.')
      if (freshHistory.some(p => p.breeding_id === payload.breeding_id)) throw new Error('Este evento reproductivo ya tiene una gestación registrada.')
      if (freshHistory.some(p => p.status === 'ACTIVE')) throw new Error('El animal ya tiene una gestación activa.')
      let temporal = context
      if (!businessTimeIsFresh(temporal.businessTimeLease)) temporal = await refreshCurrentContext()
      if (!validAttempt()) return false
      if (temporal.organization?.id !== organizationId || !temporal.can_write) throw new Error('La organización o los permisos cambiaron durante la preparación.')
      if (!businessTimeIsFresh(temporal.businessTimeLease)) throw new Error('La fecha operativa no está disponible. Recupera el contexto.')
      const invalidFresh = payloadError(payload, animalId, temporal.businessTimeLease!.snapshot.business_today, selected.date)
      if (invalidFresh) throw new Error(invalidFresh)
      setAttemptPhase(key, 'pending'); setPhase('pending'); sent = true
      const saved = await createPregnancy(payload, session.access, c.signal)
      if (!validAttempt()) return false
      setAttemptPhase(key, 'confirmed'); setPhase('confirmed'); setConfirmed(true)
      setHistory(previous => [saved, ...previous.filter(p => p.id !== saved.id)])
    } catch (cause) {
      if (!validAttempt()) return false
      if (sent && uncertainCreate(cause)) { setAttemptPhase(key, 'uncertain'); setPhase('uncertain'); busy.current = false; return false }
      finishAttempt(key); setPhase('idle'); busy.current = false
      const normalized = normalizeApiError(cause, 'No fue posible guardar la gestación.')
      setError(normalized.message); setFieldErrors(normalized.fieldErrors)
      if (sent) { busy.current = true; await synchronize() }
      return false
    } finally {
      controllers.current.delete(c)
      if (current() && getAttempt(key)?.localRevision === localRevision) {
        if (getAttempt(key)?.phase === 'pending') { setAttemptPhase(key, 'uncertain'); setPhase('uncertain'); busy.current = false }
        else if (getAttempt(key)?.phase === 'preparing') { finishAttempt(key); setPhase('idle'); busy.current = false }
      }
      c.abort()
    }
    if (current()) await synchronize()
    return current()
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
  async function openDetail(pregnancyId: string) {
    if (!current()) return
    const expected = history.find(p => p.id === pregnancyId), session = getSession()
    if (!expected || !session) return
    closeDetail()
    const c = controller(), order = ++detailReads.current
    activeDetail.current = pregnancyId; detailController.current = c
    setDetail({ status: 'loading', pregnancyId })
    const valid = () => current() && !c.signal.aborted && order === detailReads.current && activeDetail.current === pregnancyId
    try {
      const record = await getPregnancyDetail(pregnancyId, animalId, expected.breeding_id, session.access, c.signal)
      if (valid()) setDetail({ status: 'success', pregnancyId, record })
    } catch (cause) {
      if (valid()) setDetail({ status: 'error', pregnancyId, message: cause instanceof ApiError && cause.status === 404
        ? 'Esta gestación ya no está disponible.' : pregnancyErrorMessage(cause, 'No fue posible cargar el detalle de la gestación. Intenta de nuevo.') })
    } finally {
      controllers.current.delete(c)
      if (detailController.current === c) detailController.current = null
      c.abort()
    }
  }
  async function handleAbort(item: PregnancyRecord) {
    if (!current() || !writePermission.current || busy.current || getAbortAttempt(key) || getAttempt(key) || !historyReady.current
      || item.status !== 'ACTIVE' || item.animal_id !== animalId || !history.some(p => p.id === item.id && p.breeding_id === item.breeding_id)) return
    if (!window.confirm(`¿Registrar el aborto de la gestación diagnosticada el ${item.diagnosis_date.split('-').reverse().join('/')}?`)) return
    const session = getSession()
    const localRevision = ++writes.current
    const target = Object.freeze({ pregnancyId: item.id, animalId, breedingId: item.breeding_id, revision, organizationId })
    if (!session || !beginAbort(key, target, localRevision)) return
    const attempt = getAbortAttempt(key)!
    busy.current = true; setAbortState('preparing'); setAbortError(null); setAbortObserved(null); setAbortSuccess(false)
    const c = controller()
    const valid = () => current() && !c.signal.aborted && getAbortAttempt(key) === attempt && localRevision === writes.current
    let sent = false
    try {
      const fresh = await getPregnancyDetail(target.pregnancyId, target.animalId, target.breedingId, session.access, c.signal)
      if (!valid() || !writePermission.current) return
      if (fresh.status !== 'ACTIVE') {
        setHistory(previous => previous.map(p => p.id === fresh.id ? fresh : p))
        finishAbort(key); setAbortState('idle'); setAbortError('La gestación ya no está ACTIVE; no se envió el aborto.')
        await synchronize(); return
      }
      prepareAbort(key, fresh)
      if (!valid() || !writePermission.current) return
      setAbortPhase(key, 'pending'); setAbortState('pending'); sent = true
      const saved = await abortPregnancy(attempt.fresh!, session.access, c.signal)
      if (!valid()) return
      setAbortPhase(key, 'confirmed'); setAbortState('confirmed'); setAbortSuccess(true)
      setHistory(previous => previous.map(p => p.id === saved.id ? saved : p))
      if (await synchronize()) { finishAbort(key); setAbortState('idle') }
    } catch (cause) {
      if (!valid()) return
      if (sent && uncertainCreate(cause)) { setAbortPhase(key, 'uncertain'); setAbortState('uncertain'); return }
      finishAbort(key); setAbortState('idle')
      setAbortError(cause instanceof ApiError && cause.status === 404 ? 'Esta gestación ya no está disponible.'
        : pregnancyErrorMessage(cause, 'No fue posible preparar o registrar el aborto.'))
      if (sent) await synchronize()
    } finally {
      if (current() && getAbortAttempt(key) === attempt) {
        if (attempt.phase === 'pending') { setAbortPhase(key, 'uncertain'); setAbortState('uncertain') }
        else if (attempt.phase === 'preparing') { finishAbort(key); setAbortState('idle') }
      }
      if (current()) busy.current = false
      controllers.current.delete(c); c.abort()
    }
  }
  async function recoverAbort() {
    const attempt = getAbortAttempt(key), session = getSession()
    if (!current() || busy.current || !attempt || !session) return
    busy.current = true; setAbortSyncing(true); setAbortError(null)
    const c = controller(), target = attempt.target
    const valid = () => current() && !c.signal.aborted && getAbortAttempt(key) === attempt
    try {
      const fresh = await getPregnancyDetail(target.pregnancyId, target.animalId, target.breedingId, session.access, c.signal)
      if (!valid()) return
      setAbortObserved(fresh.status)
      setHistory(previous => previous.map(p => p.id === fresh.id ? fresh : p))
      const synced = await synchronize()
      if (!valid()) return
      if (synced && attempt.phase === 'confirmed') { finishAbort(key); setAbortState('idle') }
      // Current state never establishes authorship or releases an uncertain attempt.
    } catch (cause) {
      if (valid()) setAbortError(cause instanceof ApiError && cause.status === 404 ? 'Esta gestación ya no está disponible.'
        : pregnancyErrorMessage(cause, 'No fue posible consultar el resultado del aborto.'))
    } finally {
      if (current()) { busy.current = false; setAbortSyncing(false) }
      controllers.current.delete(c); c.abort()
    }
  }
  const used = new Set(history.map(p => p.breeding_id))
  const available = options?.events.filter(e => e.animal_id === animalId && !used.has(e.id)) ?? []
  const fresh = options?.animal
  const unavailable = fresh && (!fresh.is_active || fresh.gender_id !== options?.genders.find(g => g.code === 'F')?.id)
    ? 'El registro de gestaciones está disponible para hembras activas.'
    : history.some(p => p.status === 'ACTIVE') ? 'El animal ya tiene una gestación activa.'
    : options && available.length === 0 ? 'No hay eventos reproductivos disponibles para registrar una gestación.' : null
  const typeNames = new Map(options?.types.map(t => [t.id, t.name]))
  const animalNames = new Map(options?.animals.map(a => [a.id, [a.name?.trim(), a.internal_id?.trim()].filter(Boolean).join(' · ') || 'Macho sin identificación']))
  const labels = new Map(options?.events.map(e => [e.id, [e.date.split('-').reverse().join('/'), typeNames.get(e.breeding_type_id) ?? 'Tipo con referencia registrada',
    e.male_id ? animalNames.get(e.male_id) ?? 'Macho con referencia registrada' : 'Sin macho'].join(' · ')]))
  const timeReady = businessTimeIsFresh(businessTimeLease)
  const locked = !timeReady || phase !== 'idle' || abortPhase !== 'idle' || syncing || abortBusy || Boolean(syncError) || historyLoading || optionsLoading || Boolean(historyError) || Boolean(optionsError)
  function refresh() { if (!current() || busy.current) return; busy.current = true; void synchronize() }
  function recover() { if (!current() || busy.current) return; busy.current = true; void synchronize() }
  return <section className="pregnancy" aria-label="Gestación">
    <h2>Gestación</h2>
    {confirmed && <p className="pregnancy-form__success" role="status">La gestación ya fue guardada correctamente.{phase === 'confirmed' ? ' Sincroniza las lecturas antes de registrar otra operación.' : ''}</p>}
    {abortSuccess && <p role="status">El aborto ya fue registrado correctamente.</p>}
    {abortError && <p role="alert">{abortError}</p>}
    {abortPhase === 'preparing' && <p role="status">Comprobando gestación ACTIVE fresca antes de registrar el aborto...</p>}
    {abortPhase === 'pending' && <p role="status">Registrando aborto...</p>}
    {abortPhase === 'uncertain' && <p role="alert">Resultado incierto del aborto. No se puede confirmar si quedó registrado. No se repetirá el POST; las escrituras permanecen bloqueadas.</p>}
    {abortObserved && <p role="status">El registro actualmente aparece como {abortObserved === 'ABORTED' ? 'abortado' : abortObserved === 'FINISHED' ? 'finalizado' : 'activo'}.{abortPhase === 'uncertain' ? ' Esto no demuestra autoría del intento; el resultado sigue incierto.' : ''}</p>}
    {(abortPhase === 'uncertain' || abortPhase === 'confirmed') && <button type="button" disabled={abortBusy || syncing} onClick={() => void recoverAbort()}>Consultar resultado del aborto</button>}
    {error && <p role="alert">{error}</p>}
    {phase === 'preparing' && <p role="status">Comprobando relaciones y fecha operativa antes de guardar...</p>}
    {phase === 'pending' && <p role="status">Guardando gestación...</p>}
    {phase === 'uncertain' && <div><p role="alert">Resultado incierto. No se repetirá el POST. Las escrituras permanecen bloqueadas; recupera solamente las lecturas.</p>
      {readRecovered && <p>{compatible ? 'El historial contiene una gestación compatible, pero no demuestra autoría de este intento.' : 'Las lecturas no demuestran el resultado de este intento.'} El resultado sigue incierto.</p>}</div>}
    {syncError && <p role="alert">{syncError}</p>}
    {(phase === 'confirmed' || phase === 'uncertain' || syncError) && <button type="button" disabled={syncing || abortBusy} onClick={recover}>Recuperar lecturas</button>}
    {syncing && <p role="status">Actualizando datos de gestación...</p>}
    <button type="button" disabled={syncing || abortBusy || phase === 'preparing' || phase === 'pending'} onClick={refresh}>Actualizar eventos disponibles</button>
    {canWrite && <WriteOnly>
      {optionsError ? <div><p role="alert">{optionsError}</p><button type="button" disabled={phase !== 'idle' || syncing} onClick={() => setOptionsAttempt(v => v + 1)}>Reintentar opciones</button></div>
        : optionsLoading ? <p role="status">Cargando opciones de gestación...</p>
        : unavailable ? <p role="status">{unavailable}</p>
        : options && <PregnancyForm key={formVersion} animal={options.animal} events={available} eventLabels={labels} disabled={locked}
          businessToday={timeReady ? businessTimeLease!.snapshot.business_today : null} onCreate={create} fieldErrors={fieldErrors}
          onClearErrors={() => { setError(null); setFieldErrors({}) }} />}
      {!timeReady && <div><p role="status">La fecha operativa no está disponible. CREATE permanece bloqueado.</p>
        <button type="button" onClick={() => { void refreshCurrentContext().catch(() => {}) }}>Recuperar contexto</button></div>}
    </WriteOnly>}
    {historyLoading ? <p role="status">Cargando historial de gestaciones...</p>
      : historyError ? <div><p role="alert">{historyError}</p><button type="button" disabled={phase === 'preparing' || phase === 'pending' || syncing} onClick={() => setHistoryAttempt(v => v + 1)}>Actualizar historial</button></div>
      : <PregnancyHistory history={history} eventLabels={labels} disabled={phase !== 'idle' || abortPhase !== 'idle' || syncing || abortBusy || Boolean(syncError)} onAbort={handleAbort}
          detail={detail} onOpenDetail={openDetail} onCloseDetail={closeDetail} />}
  </section>
}
