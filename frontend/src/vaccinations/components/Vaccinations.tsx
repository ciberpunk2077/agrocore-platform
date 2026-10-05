import { useCallback, useRef, useState } from 'react'

import WriteOnly from '../../auth/WriteOnly'
import { useCurrentContext } from '../../auth/current-context'
import VaccinationForm from './VaccinationForm'
import VaccinationHistory from './VaccinationHistory'
import VaccinationPreparation from './VaccinationPreparation'
import VaccinationDeleteConfirmation from './VaccinationDeleteConfirmation'

interface VaccinationsProps {
  animalId: string
  birthDate: string | null
}

function Vaccinations({ animalId, birthDate }: VaccinationsProps) {
  const { currentOrganization } = useCurrentContext()
  return <AnimalVaccinations key={`${currentOrganization?.id}:${animalId}`} animalId={animalId} birthDate={birthDate} />
}

function AnimalVaccinations({ animalId, birthDate }: VaccinationsProps) {
  const [historyVersion, setHistoryVersion] = useState(0)
  const [formVersion, setFormVersion] = useState(0)
  const [result, setResult] = useState<'created' | 'updated' | 'deleted' | 'unavailable' | 'uncertain' | 'update-recheck' | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [viewingId, setViewingId] = useState<string | null>(null)
  const [createBusy, setCreateBusy] = useState(false)
  const operationLocked = useRef(false)
  const [reconciled, setReconciled] = useState(false)
  const reconciliationRequested = useRef(false)
  const updateRecheckRequested = useRef(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [createDraft, setCreateDraft] = useState(false)
  const draftLocked = useRef(false)
  const [excludedIds, setExcludedIds] = useState<string[]>([])
  const onLoaded = useCallback(() => {
    if (updateRecheckRequested.current) {
      updateRecheckRequested.current = false
      operationLocked.current = false
      setCreateBusy(false)
      setResult(null)
    }
    if (reconciliationRequested.current) {
      reconciliationRequested.current = false
      setReconciled(true)
    }
  }, [])
  const recheck = () => {
    reconciliationRequested.current = result === 'uncertain'
    setReconciled(false)
    setHistoryVersion((version) => version + 1)
  }

  return (
    <section className="vaccinations" aria-label="Vacunaciones">
      <h2>Vacunaciones</h2>
      <WriteOnly>
        {!editingId && !deletingId && result !== 'update-recheck' && <VaccinationForm key={formVersion} animalId={animalId} birthDate={birthDate}
          onDraftBegin={() => {
            if (operationLocked.current && !draftLocked.current) return false
            draftLocked.current = true
            operationLocked.current = true
            setCreateDraft(true)
            return true
          }} onDraftCancel={() => {
            draftLocked.current = false
            operationLocked.current = false
            setCreateDraft(false)
            setResult(null)
            setFormVersion((value) => value + 1)
          }}
          onBegin={() => {
            if (operationLocked.current && !draftLocked.current) return false
            operationLocked.current = true
            setCreateBusy(true)
            return true
          }} onSettled={() => { operationLocked.current = draftLocked.current; setCreateBusy(false) }} onSaved={() => {
          draftLocked.current = false
          operationLocked.current = false
          setCreateDraft(false)
          setResult('created')
          recheck()
        }} onUncertain={() => {
          reconciliationRequested.current = false
          setResult('uncertain')
          setReconciled(false)
        }} onRecheck={recheck} />}
        {editingId && <VaccinationPreparation key={editingId} vaccinationId={editingId} animalId={animalId} birthDate={birthDate}
          onCancel={() => { setEditingId(null); operationLocked.current = false }}
          onSaved={() => {
            setResult('updated')
            setEditingId(null)
            operationLocked.current = false
            recheck()
          }} onRecheck={() => {
            setEditingId(null)
            setResult('update-recheck')
            setCreateBusy(true)
            updateRecheckRequested.current = true
            recheck()
          }} />}
        {result === 'uncertain' && reconciled && <div>
          <p>El historial fue consultado. Comprueba si aparece el registro antes de continuar; esta lectura no confirma el resultado del POST anterior.</p>
          <button type="button" onClick={() => {
            setResult(null)
            operationLocked.current = false
            draftLocked.current = false
            setCreateDraft(false)
            setCreateBusy(false)
            setReconciled(false)
            setFormVersion((value) => value + 1)
          }}>Iniciar un nuevo registro</button>
        </div>}
        {deletingId && <VaccinationDeleteConfirmation key={deletingId} vaccinationId={deletingId} animalId={animalId}
          onCancel={() => { setDeletingId(null); operationLocked.current = false }}
          onDeleted={() => {
            setExcludedIds((ids) => [...ids, deletingId])
            setViewingId((id) => id === deletingId ? null : id)
            setDeletingId(null)
            operationLocked.current = false
            setResult('deleted')
            recheck()
          }} onUnavailable={() => {
            setExcludedIds((ids) => [...ids, deletingId])
            setViewingId((id) => id === deletingId ? null : id)
            setDeletingId(null)
            operationLocked.current = false
            setResult('unavailable')
            recheck()
          }} />}
      </WriteOnly>
      {viewingId && <VaccinationPreparation key={viewingId} readOnly vaccinationId={viewingId} animalId={animalId} birthDate={birthDate}
        onCancel={() => setViewingId(null)} onSaved={() => {}} onRecheck={() => {}} />}
      {result === 'created' && <p role="status">Vacunación registrada correctamente.</p>}
      {result === 'updated' && <p role="status">Vacunación actualizada correctamente.</p>}
      {result === 'deleted' && <p role="status">Vacunación eliminada correctamente.</p>}
      {result === 'unavailable' && <p role="status">La vacunación ya no está disponible.</p>}
      {result === 'update-recheck' && <p role="status">Consulta el historial antes de iniciar otra escritura. Esta lectura no confirma el resultado de la actualización anterior.</p>}
      <VaccinationHistory key={historyVersion} animalId={animalId} excludedIds={excludedIds} saved={result === 'created' || result === 'updated' || result === 'deleted' ? result : null}
        actionsDisabled={editingId !== null || deletingId !== null || createBusy || createDraft} onView={setViewingId} onDelete={(id) => {
          if (operationLocked.current || excludedIds.includes(id)) return
          operationLocked.current = true
          setViewingId(null)
          setResult(null)
          setDeletingId(id)
        }} onEdit={(id) => {
          if (operationLocked.current) return
          setViewingId(null)
          operationLocked.current = true
          setResult(null)
          setEditingId(id)
        }} onLoaded={onLoaded} />
    </section>
  )
}

export default Vaccinations
