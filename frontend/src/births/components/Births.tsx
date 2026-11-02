import { useEffect, useMemo, useRef, useState } from 'react'
import { useCurrentContext } from '../../auth/current-context'
import { getSession, getSessionRevision, subscribeSession } from '../../auth/session'
import { businessTimeIsFresh } from '../../auth/business-time'
import type { BusinessTimeLease, ResolvedCurrentContext } from '../../auth/types'
import type { Animal, Gender } from '../../animals/types'
import type { BreedingEvent } from '../../breeding/types'
import type { PregnancyRecord } from '../../pregnancy/types'
import { getAnimalBreedingHistory, getBreedingAnimal, getBreedingAnimals, getBreedingGenders, getBreedingEvent } from '../../breeding/breeding.service'
import { getAnimalPregnancyHistory, getPregnancyDetail } from '../../pregnancy/pregnancy.service'
import { normalizeApiError } from '../../lib/api-errors'
import { ApiError } from '../../lib/api'
import { birthErrorMessage, createBirth, getAnimalBirthHistory, getBirthDetail, uncertainCreate } from '../births.service'
import { abandonScope, attemptKey, beginPreparation, finishAttempt, getAttempt, preparePayload, setAttemptPhase, type CreatePhase } from '../create-protocol'
import { matchesPayload, normalizedPayload, payloadError } from '../validation'
import type { BirthCreatePayload, BirthRecord, BirthDetailState } from '../types'
import BirthForm from './BirthForm'
import BirthHistory from './BirthHistory'

interface Options { pregnancies: PregnancyRecord[]; breedings: BreedingEvent[]; animals: Animal[]; genders: Gender[]; mother: Animal }
interface BirthProps { animal: Animal; onPregnancyChanged?: () => void }
export default function Births({ animal, onPregnancyChanged }: BirthProps) {
  const context = useCurrentContext()
  const [revision, setRevision] = useState(getSessionRevision)
  useEffect(() => subscribeSession(() => setRevision(getSessionRevision())), [])
  if (context.status !== 'loaded' || !context.currentOrganization) return <p role="status">Cargando contexto de partos...</p>
  return <BirthScope key={`${revision}:${context.currentOrganization.id}:${animal.id}:${context.canWrite}`}
    animal={animal} revision={revision} organizationId={context.currentOrganization.id} canWrite={context.canWrite}
    businessTimeLease={context.businessTimeLease} refreshCurrentContext={context.refreshCurrentContext}
    isCurrentOrganization={context.isCurrentOrganization} onPregnancyChanged={onPregnancyChanged} />
}
export interface ScopeProps extends BirthProps {
  revision: number; organizationId: string; canWrite: boolean
  businessTimeLease: BusinessTimeLease | null
  refreshCurrentContext: () => Promise<ResolvedCurrentContext>
  isCurrentOrganization: (id: string) => boolean
}
export function BirthScope({ animal, revision, organizationId, canWrite, businessTimeLease, refreshCurrentContext, isCurrentOrganization, onPregnancyChanged }: ScopeProps) {
  const motherId = animal.id, key = attemptKey(revision, organizationId, motherId)
  const [phase, setPhase] = useState<CreatePhase>(() => getAttempt(key)?.phase === 'pending' ? 'uncertain' : getAttempt(key)?.phase ?? 'idle')
  const [history, setHistory] = useState<BirthRecord[]>([])
  const [detail, setDetail] = useState<BirthDetailState>({ status: 'idle' })
  const detailReads = useRef(0)
  const activeDetail = useRef<string | null>(null)
  const detailController = useRef<AbortController | null>(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [readAttempt, setReadAttempt] = useState(0)
  const [options, setOptions] = useState<Options | null>(null)
  const [optionsLoading, setOptionsLoading] = useState(canWrite)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  const [optionAttempt, setOptionAttempt] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const [confirmed, setConfirmed] = useState(() => getAttempt(key)?.phase === 'confirmed')
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [observation, setObservation] = useState<string | null>(null)
  const [formVersion, setFormVersion] = useState(0)
  const alive = useRef(false), busy = useRef(false), permission = useRef(canWrite)
  const historyReady = useRef(false), optionsReady = useRef(false)
  const reads = useRef(0), optionReads = useRef(0), formGeneration = useRef(0)
  const controllers = useRef(new Set<AbortController>())
  useEffect(() => { permission.current = canWrite }, [canWrite])
  const current = () => alive.current && getSessionRevision() === revision && isCurrentOrganization(organizationId)
  const controller = () => { const c = new AbortController(); controllers.current.add(c); return c }
  useEffect(() => {
    const activeControllers = controllers.current
    alive.current = true
    return () => { alive.current = false; abandonScope(key); activeControllers.forEach(c => c.abort()); activeControllers.clear() }
  }, [key])
  useEffect(() => {
    const c = controller(), order = ++reads.current
    historyReady.current = false
    async function load() {
      setHistoryLoading(true); setHistoryError(null)
      const session = getSession()
      if (!session || !current()) return
      try {
        const result = await getAnimalBirthHistory(motherId, session.access, c.signal)
        if (current() && !c.signal.aborted && order === reads.current) { setHistory(result); historyReady.current = true }
      } catch (cause) {
        if (current() && !c.signal.aborted && order === reads.current) setHistoryError(birthErrorMessage(cause, 'No fue posible cargar el historial de partos.'))
      } finally {
        if (current() && !c.signal.aborted && order === reads.current) setHistoryLoading(false)
        controllers.current.delete(c)
      }
    }
    void load()
    return () => c.abort()
    // The wrapper remounts scopes; each completion also checks revision and generation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readAttempt])
  useEffect(() => {
    if (!canWrite) return
    const c = controller(), order = ++optionReads.current
    optionsReady.current = false
    async function load() {
      setOptionsLoading(true); setOptionsError(null)
      const session = getSession()
      if (!session || !current()) return
      try {
        const [pregnancies, breedings, animals, genders, mother] = await Promise.all([
          getAnimalPregnancyHistory(motherId, session.access, c.signal), getAnimalBreedingHistory(motherId, session.access, c.signal),
          getBreedingAnimals(session.access, c.signal), getBreedingGenders(session.access, c.signal), getBreedingAnimal(motherId, session.access, c.signal),
        ])
        if (current() && !c.signal.aborted && order === optionReads.current) { setOptions({ pregnancies, breedings, animals, genders, mother }); optionsReady.current = true }
      } catch (cause) {
        if (current() && !c.signal.aborted && order === optionReads.current) setOptionsError(birthErrorMessage(cause, 'No fue posible cargar las opciones del parto.'))
      } finally {
        if (current() && !c.signal.aborted && order === optionReads.current) setOptionsLoading(false)
        controllers.current.delete(c)
      }
    }
    void load()
    return () => c.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optionAttempt])
  async function synchronize() {
    const session = getSession()
    if (!session || !current()) return false
    const c = controller(), order = ++reads.current
    // Invalidate an older options load before publishing refreshed options.
    const optionsOrder = ++optionReads.current
    historyReady.current = false; optionsReady.current = false
    setSyncing(true); setSyncError(null); setObservation(null)
    try {
      const rows = await getAnimalBirthHistory(motherId, session.access, c.signal)
      if (!current() || c.signal.aborted || order !== reads.current) return false
      setHistory(rows); setHistoryError(null); setHistoryLoading(false); historyReady.current = true
      const [pregnancies, animals] = await Promise.all([
        getAnimalPregnancyHistory(motherId, session.access, c.signal), getBreedingAnimals(session.access, c.signal),
      ])
      if (!current() || c.signal.aborted || order !== reads.current || optionsOrder !== optionReads.current) return false
      setOptions(previous => previous ? { ...previous, pregnancies, animals } : previous)
      optionsReady.current = Boolean(options)
      const attempt = getAttempt(key)
      if (attempt) {
        const found = rows.find(b => b.pregnancy_id === attempt.target.pregnancy_id)
        const pregnancy = pregnancies.find(p => p.id === attempt.target.pregnancy_id)
        if (found) {
          const compatible = matchesPayload(found, attempt.payload ?? attempt.target)
          if (found.calf_id) await getBreedingAnimal(found.calf_id, session.access, c.signal)
          if (!current() || c.signal.aborted || order !== reads.current) return false
          setObservation(compatible ? 'El historial contiene un parto compatible. Esto no demuestra autoría del intento; su resultado sigue incierto.'
            : 'El historial contiene un parto para esta gestación con datos diferentes; su resultado sigue incierto.')
        } else setObservation(`No se encontró el parto. Estado actual de la gestación: ${pregnancy?.status ?? 'no disponible'}. No se repetirá el envío.`)
        if (attempt.phase === 'confirmed') { finishAttempt(key); setPhase('idle'); setObservation(null); formGeneration.current++; setFormVersion(formGeneration.current) }
      }
      onPregnancyChanged?.()
      return true
    } catch (cause) {
      if (current() && !c.signal.aborted && order === reads.current) setSyncError(birthErrorMessage(cause, 'No fue posible sincronizar los datos. Recupera solamente las lecturas.'))
      return false
    } finally {
      if (current() && !c.signal.aborted && order === reads.current) { setSyncing(false); busy.current = false }
      controllers.current.delete(c); c.abort()
    }
  }
  async function create(data: BirthCreatePayload): Promise<boolean> {
    if (!current() || !permission.current || !canWrite || busy.current || getAttempt(key) || formVersion !== formGeneration.current
      || !historyReady.current || !optionsReady.current || !businessTimeIsFresh(businessTimeLease)) return false
    const target = Object.freeze(normalizedPayload(data))
    const invalid = payloadError(target, motherId, businessTimeLease!.snapshot.business_today)
    if (invalid) { setError(invalid); return false }
    const selected = options?.pregnancies.find(p => p.id === target.pregnancy_id)
    if (!selected || selected.animal_id !== motherId) { setError('La gestación seleccionada no está disponible.'); return false }
    if (!window.confirm('¿Registrar este parto y finalizar la gestación seleccionada?')) return false
    if (!current() || !permission.current) return false
    const session = getSession(), attempt = session ? beginPreparation(key, target) : null
    if (!session || !attempt) return false
    busy.current = true; setPhase('preparing'); setConfirmed(false); setError(null); setFieldErrors({}); setSyncError(null); setObservation(null)
    const c = controller()
    const valid = () => current() && !c.signal.aborted && getAttempt(key) === attempt
    let sent = false
    try {
      const [pregnancy, mother, rows, genders, calf, context] = await Promise.all([
        getPregnancyDetail(target.pregnancy_id, motherId, selected.breeding_id, session.access, c.signal),
        getBreedingAnimal(motherId, session.access, c.signal), getAnimalBirthHistory(motherId, session.access, c.signal),
        target.calf_gender_id !== null ? getBreedingGenders(session.access, c.signal) : Promise.resolve([]),
        target.calf_id !== null ? getBreedingAnimal(target.calf_id, session.access, c.signal) : Promise.resolve(null), refreshCurrentContext(),
      ])
      if (!valid() || !permission.current) return false
      if (!mother.is_active) throw new Error('La madre ya no está activa.')
      if (pregnancy.status !== 'ACTIVE') throw new Error('La gestación ya no está ACTIVE.')
      if (rows.some(b => b.pregnancy_id === target.pregnancy_id)) throw new Error('Esta gestación ya tiene un parto registrado.')
      if (target.calf_gender_id !== null && !genders.some(g => g.id === target.calf_gender_id)) throw new Error('El sexo seleccionado ya no está disponible.')
      if (calf && (!calf.is_active || calf.id === motherId || (calf.mother_id !== null && calf.mother_id !== motherId))) throw new Error('La cría existente ya no está disponible para esta madre.')
      const breeding = await getBreedingEvent(pregnancy.breeding_id, motherId, session.access, c.signal)
      let freshContext = context
      if (!businessTimeIsFresh(freshContext.businessTimeLease)) freshContext = await refreshCurrentContext()
      if (!valid() || !permission.current) return false
      if (freshContext.organization?.id !== organizationId || !freshContext.can_write) throw new Error('La organización o los permisos cambiaron durante la preparación.')
      if (!businessTimeIsFresh(freshContext.businessTimeLease)) throw new Error('La fecha operativa no está disponible.')
      const payload = Object.freeze(normalizedPayload(target))
      const invalidFresh = payloadError(payload, motherId, freshContext.businessTimeLease!.snapshot.business_today, pregnancy.diagnosis_date, breeding.date)
      if (invalidFresh) throw new Error(invalidFresh)
      preparePayload(key, payload)
      if (!valid() || !permission.current) return false
      setAttemptPhase(key, 'pending'); setPhase('pending'); sent = true
      const saved = await createBirth(attempt.payload!, session.access, c.signal)
      if (!valid()) return false
      setAttemptPhase(key, 'confirmed'); setPhase('confirmed'); setConfirmed(true)
      setHistory(previous => [saved, ...previous.filter(b => b.id !== saved.id)])
      onPregnancyChanged?.()
    } catch (cause) {
      if (!valid()) return false
      if (sent && uncertainCreate(cause)) { setAttemptPhase(key, 'uncertain'); setPhase('uncertain'); busy.current = false; return false }
      finishAttempt(key); setPhase('idle'); busy.current = false
      const normalized = normalizeApiError(cause, 'No fue posible preparar o registrar el parto.')
      setError(normalized.message); setFieldErrors(normalized.fieldErrors)
      if (sent) { busy.current = true; await synchronize() }
      return false
    } finally {
      if (current() && getAttempt(key) === attempt) {
        if (attempt.phase === 'pending') { setAttemptPhase(key, 'uncertain'); setPhase('uncertain'); busy.current = false }
        else if (attempt.phase === 'preparing') { finishAttempt(key); setPhase('idle'); busy.current = false }
      }
      controllers.current.delete(c); c.abort()
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
  async function openDetail(birthId: string) {
    if (!current()) return
    const session = getSession()
    if (!session || !history.some(b => b.id === birthId)) return
    closeDetail()
    const c = controller(), order = ++detailReads.current
    activeDetail.current = birthId; detailController.current = c
    setDetail({ status: 'loading', birthId })
    const valid = () => current() && !c.signal.aborted && order === detailReads.current && activeDetail.current === birthId
    try {
      const record = await getBirthDetail(birthId, motherId, session.access, c.signal)
      if (valid()) setDetail({ status: 'success', birthId, record })
    } catch (cause) {
      if (valid()) setDetail({ status: 'error', birthId, message: cause instanceof ApiError && cause.status === 404
        ? 'Este parto ya no está disponible.' : birthErrorMessage(cause, 'No fue posible cargar el detalle del parto. Intenta de nuevo.') })
    } finally {
      controllers.current.delete(c)
      if (detailController.current === c) detailController.current = null
      c.abort()
    }
  }
  const pregnancies = options?.pregnancies
  // DETAIL renders must not look like new CREATE source data to BirthForm.
  const available = useMemo(() => pregnancies?.filter(p => p.animal_id === motherId && p.status === 'ACTIVE'
    && !history.some(b => b.pregnancy_id === p.id)) ?? [], [pregnancies, history, motherId])
  const timeReady = businessTimeIsFresh(businessTimeLease)
  const unavailable = options && (!options.mother.is_active || options.mother.gender_id !== options.genders.find(g => g.code === 'F')?.id)
    ? 'El registro de partos está disponible para hembras activas.' : options && !available.length ? 'No hay una gestación activa disponible.' : null
  const locked = phase !== 'idle' || syncing || Boolean(syncError) || historyLoading || Boolean(historyError) || optionsLoading || Boolean(optionsError) || !timeReady
  function recover() { if (!current() || busy.current) return; busy.current = true; void synchronize() }
  return <section className="births" aria-label="Partos">
    <h2>Partos</h2>
    {confirmed && <p role="status">El parto ya fue registrado correctamente.</p>}
    {error && <p role="alert">{error}</p>}
    {phase === 'preparing' && <p role="status">Comprobando relaciones y fecha operativa...</p>}
    {phase === 'pending' && <p role="status">Registrando parto...</p>}
    {phase === 'uncertain' && <p role="alert">Resultado incierto. No se puede confirmar si el parto quedó registrado. No se repetirá el envío; CREATE permanece bloqueado.</p>}
    {observation && <p role="status">{observation}</p>}
    {syncError && <p role="alert">{syncError}</p>}
    {(phase === 'confirmed' || phase === 'uncertain' || syncError) && <button type="button" disabled={syncing} onClick={recover}>Recuperar lecturas</button>}
    {syncing && <p role="status">Actualizando datos de partos...</p>}
    {canWrite && <>
      {optionsError ? <div><p role="alert">{optionsError}</p><button type="button" disabled={phase !== 'idle' || syncing} onClick={() => setOptionAttempt(v => v + 1)}>Reintentar opciones</button></div>
        : optionsLoading ? <p role="status">Cargando opciones del parto...</p>
        : unavailable ? <p role="status">{unavailable}</p>
        : options && <BirthForm key={formVersion} animal={options.mother} pregnancies={available} breedings={options.breedings} animals={options.animals} genders={options.genders}
          disabled={locked} businessToday={timeReady ? businessTimeLease!.snapshot.business_today : null} fieldErrors={fieldErrors}
          onClearErrors={() => { if (current()) { setError(null); setFieldErrors({}) } }} onCreate={create} />}
      {!timeReady && <div><p role="status">La fecha operativa no está disponible. CREATE permanece bloqueado.</p><button type="button" onClick={() => { void refreshCurrentContext().catch(() => {}) }}>Recuperar contexto</button></div>}
    </>}
    {historyLoading && <p role="status">Cargando historial de partos...</p>}
    {historyError && <div><p role="alert">{historyError}</p><button type="button" disabled={phase === 'preparing' || phase === 'pending' || syncing} onClick={() => setReadAttempt(v => v + 1)}>Actualizar historial</button></div>}
    <BirthHistory history={history} animals={options?.animals ?? []} genders={options?.genders ?? []} disabled={phase !== 'idle' || syncing}
      detail={detail} onOpenDetail={openDetail} onCloseDetail={closeDetail} />
  </section>
}
