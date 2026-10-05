import { useEffect, useRef, useState } from 'react'
import { useCurrentContext } from '../../auth/current-context'
import { getSession, getSessionRevision, subscribeSession } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import type { Animal, Farm, Lot } from '../../animals/types'
import { createAnimalMovement, deleteAnimalMovement, getAnimalMovement, updateAnimalMovement, getAnimalMovementHistory, getMovementAnimal, getMovementFarms, getMovementLots, getMovementTypes, uncertainCreate } from '../animal-movements.service'
import { abandonPending, attemptKey, beginAttempt, beginDeleteAttempt, reconcileDeletion, finishAttempt, getAttempt, setAttemptPhase, type CreatePhase, type DeleteSnapshot } from '../create-protocol'
import type { AnimalMovement, AnimalMovementCreatePayload, AnimalMovementUpdatePayload, MovementType } from '../types'
import { isAnimal, isHistory, isMovement, matchesAttempt, validDate } from '../validation'
import { updateError } from '../update-validation'
import AnimalMovementDeleteConfirmation from './AnimalMovementDeleteConfirmation'
import AnimalMovementDetail from './AnimalMovementDetail'
import AnimalMovementEditForm from './AnimalMovementEditForm'
import AnimalMovementForm from './AnimalMovementForm'
import AnimalMovementHistory from './AnimalMovementHistory'

interface Props { animalId: string; animal: Animal; onAnimalUpdated: (animal: Animal) => void }
export default function AnimalMovements(props: Props) {
  const context = useCurrentContext()
  const [revision, setRevision] = useState(getSessionRevision)
  useEffect(() => subscribeSession(() => setRevision(getSessionRevision())), [])
  if (context.status !== 'loaded' || !context.currentOrganization) return <p role="status">Cargando contexto de movimientos...</p>
  return <MovementScope key={`${revision}:${context.currentOrganization.id}:${props.animalId}:${context.canWrite}`} {...props}
    revision={revision} organizationId={context.currentOrganization.id} canWrite={context.canWrite} />
}

export function MovementScope({ animalId, animal, onAnimalUpdated, revision, organizationId, canWrite }: Props & { revision: number; organizationId: string; canWrite: boolean }) {
  const key = attemptKey(revision, organizationId, animalId)
  const [phase, setPhase] = useState<CreatePhase>(() => getAttempt(key)?.phase === 'pending' ? 'uncertain' : getAttempt(key)?.phase ?? 'idle')
  const [operation, setOperation] = useState<'create' | 'update' | 'delete'>(() => getAttempt(key)?.kind ?? 'create')
  const [detailId, setDetailId] = useState<string | null>(null)
  const [editorId, setEditorId] = useState<string | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const deleting = useRef<string | null>(null)
  const [absenceReconciled, setAbsenceReconciled] = useState(() => getAttempt(key)?.reconciled ?? false)
  const editing = useRef<string | null>(null)
  const [history, setHistory] = useState<AnimalMovement[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [catalogs, setCatalogs] = useState<{ types: MovementType[]; farms: Farm[]; lots: Lot[] } | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [catalogAttempt, setCatalogAttempt] = useState(0)
  const [historyAttempt, setHistoryAttempt] = useState(0)
  const [freshAnimal, setFreshAnimal] = useState(animal)
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [readRecovered, setReadRecovered] = useState(false)
  const [formVersion, setFormVersion] = useState(0)
  const animalSnapshot = useRef(animal)
  const historySnapshot = useRef<AnimalMovement[]>([])
  const alive = useRef(false)
  const busy = useRef(false)
  const reads = useRef(0)
  const controllers = useRef(new Set<AbortController>())
  const current = () => alive.current && getSessionRevision() === revision
  const controller = () => { const c = new AbortController(); controllers.current.add(c); return c }

  useEffect(() => {
    const activeControllers = controllers.current
    alive.current = true
    return () => {
      alive.current = false
      abandonPending(key)
      activeControllers.forEach(c => c.abort())
      activeControllers.clear()
    }
  }, [key])

  useEffect(() => {
    const c = controller()
    const order = ++reads.current
    async function load() {
      const session = getSession()
      if (!session || !current()) return
      setHistoryLoading(true)
      setHistoryError(null)
      try {
        const result = await getAnimalMovementHistory(animalId, session.access, c.signal)
        if (current() && !c.signal.aborted && order === reads.current) {
          historySnapshot.current = result
          setHistory(result)
        }
      } catch (cause) {
        if (current() && !c.signal.aborted && order === reads.current) setHistoryError(normalizeApiError(cause, 'No fue posible cargar el historial de movimientos.').message)
      } finally {
        if (current() && !c.signal.aborted && order === reads.current) setHistoryLoading(false)
        controllers.current.delete(c)
      }
    }
    void load()
    return () => { c.abort() }
    // Scope is remounted whenever animal/session/tenant changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyAttempt])

  useEffect(() => {
    const c = controller()
    async function load() {
      const session = getSession()
      if (!session || !current()) return
      setCatalogError(null)
      try {
        const [types, farms, lots] = await Promise.all([
          getMovementTypes(session.access, c.signal), getMovementFarms(session.access, c.signal), getMovementLots(session.access, organizationId, c.signal),
        ])
        if (current() && !c.signal.aborted) setCatalogs({ types, farms, lots })
      } catch (cause) {
        if (current() && !c.signal.aborted) setCatalogError(normalizeApiError(cause, 'No fue posible cargar los catálogos para registrar movimientos.').message)
      } finally { controllers.current.delete(c) }
    }
    void load()
    return () => { c.abort() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogAttempt])

  async function synchronize(reconcileAbsence = false) {
    const session = getSession()
    if (!session || !current()) return
    const c = controller()
    const order = ++reads.current
    setSyncing(true)
    setReadRecovered(false)
    setSyncError(null)
    try {
      const [movements, updated] = await Promise.all([
        getAnimalMovementHistory(animalId, session.access, c.signal), getMovementAnimal(animalId, session.access, c.signal),
      ])
      if (!current() || c.signal.aborted || order !== reads.current) return
      const attempt = getAttempt(key)
      if (attempt?.kind === 'delete') {
        if (!updated.is_active || movements.some(m => m.id === attempt.movementId)) {
          setSyncError('No se confirmó una ausencia sincronizada con Animal activo. Las escrituras siguen bloqueadas.')
          return
        }
        if (reconcileAbsence) {
          reconcileDeletion(key)
          setAbsenceReconciled(true)
          setPhase('confirmed')
        }
      }
      setHistory(movements)
      historySnapshot.current = movements
      setHistoryError(null)
      setHistoryLoading(false)
      setFreshAnimal(updated)
      animalSnapshot.current = updated
      onAnimalUpdated(updated)
      setReadRecovered(true)
      if (getAttempt(key)?.phase === 'confirmed') {
        finishAttempt(key)
        setPhase('idle')
        setFormVersion(v => v + 1)
        setEditorId(null)
        editing.current = null
        setDeleteId(null)
        deleting.current = null
      }
    } catch (cause) {
      if (current() && !c.signal.aborted && order === reads.current) setSyncError(normalizeApiError(cause, 'No fue posible sincronizar historial y Animal. Reintenta únicamente la lectura.').message)
    } finally {
      controllers.current.delete(c)
      if (current() && !c.signal.aborted) { setSyncing(false); busy.current = false }
      // Cancel the other read if Promise.all rejected before it finished.
      c.abort()
    }
  }

  async function create(payload: AnimalMovementCreatePayload) {
    if (!current() || busy.current || editing.current || deleting.current || !canWrite || historyLoading || historyError || !catalogs || !animalSnapshot.current.is_active
      || payload.animal_id !== animalId || getAttempt(key)) return
    const snapshot = animalSnapshot.current
    const code = catalogs.types.find(t => t.id === payload.movement_type_id)?.code
    const needsOrigin = code === 'TRANSFER' || code === 'EXIT' || code === 'SALE'
    const latestDate = historySnapshot.current.reduce((latest, item) => item.date > latest ? item.date : latest, '')
    // A handler captured before synchronization must not submit stale location/status.
    if (!validDate(payload.date) || payload.date > new Date().toISOString().slice(0, 10) || payload.date <= latestDate
      || (needsOrigin && (payload.origin_farm_id !== snapshot.farm_id || payload.origin_lot_id !== snapshot.lot_id))
      || ((code === 'ENTRY' || code === 'PURCHASE') && (snapshot.farm_id || snapshot.lot_id))) {
      throw new Error('El formulario no corresponde a los datos actuales del animal.')
    }
    if (!beginAttempt(key, payload)) return
    const session = getSession()
    if (!session) { finishAttempt(key); return }
    busy.current = true
    const c = controller()
    setAbsenceReconciled(false)
    setOperation('create')
    setPhase('pending')
    setReadRecovered(false)
    try {
      const saved = await createAnimalMovement(payload, snapshot.status_id, session.access, c.signal)
      if (!current() || c.signal.aborted) return
      setAttemptPhase(key, 'confirmed')
      setPhase('confirmed')
      historySnapshot.current = [saved, ...historySnapshot.current.filter(item => item.id !== saved.id)]
      setHistory(items => [saved, ...items.filter(item => item.id !== saved.id)])
    } catch (cause) {
      if (!current() || c.signal.aborted) return
      if (uncertainCreate(cause)) {
        setAttemptPhase(key, 'uncertain')
        setPhase('uncertain')
        busy.current = false
        return
      }
      finishAttempt(key)
      setPhase('idle')
      busy.current = false
      throw cause
    } finally { controllers.current.delete(c) }
    if (current()) await synchronize()
  }

  function openEditor(movementId: string) {
    if (!current() || !canWrite || busy.current || editing.current || deleting.current || getAttempt(key) || !catalogs) return
    editing.current = movementId
    setEditorId(movementId)
    setDetailId(null)
  }
  function cancelEditor() {
    if (getAttempt(key) || busy.current) return
    editing.current = null
    setEditorId(null)
  }
  async function update(record: AnimalMovement, payload: AnimalMovementUpdatePayload, preparedHistory = historySnapshot.current) {
    if (!current() || !canWrite || busy.current || deleting.current || getAttempt(key) || editing.current !== record.id || !catalogs || !animalSnapshot.current.is_active) return
    if (record.animal_id !== animalId) return
    if (!isHistory(preparedHistory, animalId) || preparedHistory[0]?.id !== record.id) throw new Error('Solo puede editarse el último movimiento activo.')
    const previousDate = preparedHistory.find(m => m.id !== record.id)?.date ?? ''
    const invalid = updateError(payload, record, previousDate, catalogs.types, catalogs.farms, catalogs.lots)
    if (invalid) throw new Error(invalid)
    const session = getSession()
    if (!session || !beginAttempt(key, payload, { movementId: record.id, originStatusId: record.origin_status_id })) return
    busy.current = true
    const c = controller()
    setAbsenceReconciled(false)
    setOperation('update'); setPhase('pending'); setReadRecovered(false); setSyncError(null)
    try {
      const saved = await updateAnimalMovement(record.id, payload, record.origin_status_id, session.access, c.signal)
      if (!current() || c.signal.aborted) return
      setAttemptPhase(key, 'confirmed'); setPhase('confirmed')
      historySnapshot.current = [saved, ...historySnapshot.current.filter(m => m.id !== saved.id)]
      setHistory(historySnapshot.current)
    } catch (cause) {
      if (!current() || c.signal.aborted) return
      if (uncertainCreate(cause)) {
        setAttemptPhase(key, 'uncertain'); setPhase('uncertain'); busy.current = false
        return
      }
      finishAttempt(key); setPhase('idle'); busy.current = false
      throw cause
    } finally { controllers.current.delete(c) }
    if (current()) await synchronize()
  }
  function openDelete(movementId: string) {
    if (!current() || !canWrite || busy.current || editing.current || deleting.current || getAttempt(key)) return
    if (historySnapshot.current[0]?.id !== movementId) return
    deleting.current = movementId
    setDeleteId(movementId)
    setDetailId(null)
  }
  function cancelDelete() {
    if (!current() || busy.current || getAttempt(key)) return
    deleting.current = null
    setDeleteId(null)
  }
  async function remove(snapshot: DeleteSnapshot) {
    if (!current() || !canWrite || busy.current || editing.current || getAttempt(key) || deleting.current !== snapshot.movement.id) return
    if (snapshot.revision !== revision || snapshot.organizationId !== organizationId
      || !isMovement(snapshot.movement, animalId) || !isAnimal(snapshot.animal, animalId) || !snapshot.animal.is_active
      || !isHistory(snapshot.history, animalId) || snapshot.history[0]?.id !== snapshot.movement.id) return
    const session = getSession()
    if (!session || !beginDeleteAttempt(key, snapshot)) return
    busy.current = true
    const c = controller()
    setOperation('delete'); setAbsenceReconciled(false); setPhase('pending'); setReadRecovered(false); setSyncError(null)
    try {
      await deleteAnimalMovement(snapshot.movement.id, session.access, c.signal)
      if (!current() || c.signal.aborted) return
      setAttemptPhase(key, 'confirmed'); setPhase('confirmed')
      historySnapshot.current = historySnapshot.current.filter(m => m.id !== snapshot.movement.id)
      setHistory(historySnapshot.current)
    } catch (cause) {
      if (!current() || c.signal.aborted) return
      if (uncertainCreate(cause) || (cause instanceof ApiError && cause.status === 404)) {
        setAttemptPhase(key, 'uncertain'); setPhase('uncertain'); busy.current = false
        return
      }
      finishAttempt(key); setPhase('idle'); busy.current = false
      throw cause
    } finally { controllers.current.delete(c) }
    if (current()) await synchronize()
  }
  async function recover() {
    if (!current() || busy.current) return
    const attempt = getAttempt(key)
    if (!attempt) return
    busy.current = true
    if (attempt.kind === 'delete' && attempt.phase === 'uncertain') {
      const session = getSession()
      if (!session || !attempt.movementId) { busy.current = false; return }
      const c = controller()
      setSyncing(true); setSyncError(null)
      let absent = false
      try {
        await getAnimalMovement(attempt.movementId, animalId, session.access, c.signal)
        if (current() && !c.signal.aborted) setSyncError('El movimiento sigue disponible. El resultado es incierto; no se repetirá la eliminación.')
      } catch (cause) {
        if (!current() || c.signal.aborted) return
        if (cause instanceof ApiError && cause.status === 404) absent = true
        else setSyncError(normalizeApiError(cause, 'No fue posible comprobar la ausencia. Las escrituras siguen bloqueadas.').message)
      } finally {
        controllers.current.delete(c)
        if (current() && !c.signal.aborted) { setSyncing(false); busy.current = false }
        c.abort()
      }
      if (absent && current()) { busy.current = true; await synchronize(true) }
      return
    }
    if (attempt.kind === 'update' && attempt.phase === 'uncertain') {
      const session = getSession()
      if (!session || !attempt.movementId) { busy.current = false; return }
      const c = controller()
      setSyncing(true); setSyncError(null)
      try {
        const fresh = await getAnimalMovement(attempt.movementId, animalId, session.access, c.signal)
        if (!current() || c.signal.aborted) return
        if (!matchesAttempt(fresh, attempt.payload, attempt.originStatusId ?? null)) {
          setSyncError('El registro leído no coincide con el intento. El resultado sigue incierto y las escrituras permanecen bloqueadas.')
          return
        }
        setAttemptPhase(key, 'confirmed'); setPhase('confirmed')
      } catch (cause) {
        if (current() && !c.signal.aborted) setSyncError(normalizeApiError(cause, 'No fue posible reconciliar la actualización. Las escrituras permanecen bloqueadas.').message)
        return
      } finally {
        controllers.current.delete(c)
        if (current() && !c.signal.aborted) { setSyncing(false); busy.current = false }
      }
      if (!current()) return
      busy.current = true
    }
    await synchronize()
  }

  const success = phase === 'confirmed' || (phase === 'idle' && readRecovered)
  const lastDate = history.reduce((latest, item) => item.date > latest ? item.date : latest, '')
  return <section className="animal-movements" aria-label="Movimientos">
    <h2>Movimientos</h2>
    {success && <p role="status">{operation === 'delete' ? (absenceReconciled ? 'Estado reconciliado: movimiento ausente del historial activo; no se atribuye esta ausencia al intento.' : 'Eliminación del movimiento confirmada.') : operation === 'update' ? 'Actualización del movimiento confirmada.' : 'Movimiento registrado correctamente.'}</p>}
    {phase === 'confirmed' && <p role="status">La escritura está confirmada; falta sincronizar historial y Animal antes de otra operación.</p>}
    {phase === 'pending' && <p role="status">Guardando movimiento...</p>}
    {phase === 'uncertain' && <p role="alert">{operation === 'delete'
      ? 'Eliminación incierta: las escrituras están bloqueadas. Solo pueden recuperarse lecturas; no se repetirá la eliminación.'
      : operation === 'update'
      ? 'Actualización incierta: las escrituras están bloqueadas. Reconciliar consulta el registro; una diferencia no demuestra que la actualización haya fallado.'
      : 'Resultado incierto: no podemos confirmar si se registró el movimiento. La creación permanece bloqueada para evitar duplicados. Recupera las lecturas; un registro compatible no demuestra que este intento lo haya creado.'}</p>}
    {phase === 'uncertain' && readRecovered && <p role="status">Lecturas recuperadas. El intento sigue incierto y la creación permanece bloqueada.</p>}
    {syncError && <p role="alert">{syncError}</p>}
    {(phase === 'confirmed' || phase === 'uncertain') && <button type="button" disabled={syncing} onClick={() => void recover()}>{syncing ? 'Sincronizando...' : operation === 'delete' && phase === 'uncertain' ? 'Reconciliar ausencia' : operation === 'update' && phase === 'uncertain' ? 'Reconciliar actualización' : 'Recuperar lecturas'}</button>}
    {historyLoading && <p role="status">Cargando historial de movimientos...</p>}
    {historyError && <div><p role="alert">{historyError}</p><button type="button" disabled={syncing || phase === 'pending'} onClick={() => setHistoryAttempt(v => v + 1)}>Reintentar historial</button></div>}
    <AnimalMovementHistory history={history} types={catalogs?.types ?? []} farms={catalogs?.farms ?? []} lots={catalogs?.lots ?? []}
      onDetail={id => setDetailId(id)} onEdit={canWrite ? openEditor : undefined} onDelete={canWrite ? openDelete : undefined}
      deleteDisabled={phase !== 'idle' || syncing || !!deleteId || !!editorId || historyLoading || !!historyError}
      editDisabled={phase !== 'idle' || syncing || !!deleteId || !!editorId || !catalogs || historyLoading || !!historyError} />
    {detailId && <AnimalMovementDetail key={detailId} movementId={detailId} animalId={animalId} revision={revision} organizationId={organizationId}
      types={catalogs?.types ?? []} farms={catalogs?.farms ?? []} lots={catalogs?.lots ?? []} animal={freshAnimal} onClose={() => setDetailId(null)} />}
    {canWrite && editorId && catalogs && <AnimalMovementEditForm key={editorId} movementId={editorId} animalId={animalId}
      revision={revision} organizationId={organizationId} {...catalogs} animalActive={freshAnimal.is_active}
      disabled={phase !== 'idle' || syncing} onCancel={cancelEditor} onSave={update} />}
    {canWrite && deleteId && <AnimalMovementDeleteConfirmation key={deleteId} movementId={deleteId} animalId={animalId}
      revision={revision} organizationId={organizationId} types={catalogs?.types ?? []} farms={catalogs?.farms ?? []} lots={catalogs?.lots ?? []}
      disabled={phase !== 'idle' || syncing} onCancel={cancelDelete} onConfirm={remove} />}
    {catalogError && <div><p role="alert">{catalogError}</p><button type="button" onClick={() => setCatalogAttempt(v => v + 1)}>Reintentar catálogos</button></div>}
    {canWrite && (catalogs ? <AnimalMovementForm key={formVersion} animalId={animalId} animal={freshAnimal}
      {...catalogs} lastDate={lastDate} disabled={phase !== 'idle' || syncing || !!deleteId || !!editorId || historyLoading || !!historyError} onCreate={create} />
      : <p role="status">Preparando registro de movimientos...</p>)}
  </section>
}
