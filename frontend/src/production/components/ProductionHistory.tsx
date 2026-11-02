import { useEffect, useState } from 'react'
import WriteOnly from '../../auth/WriteOnly'
import ProductionForm from './ProductionForm'
import ProductionDeleteConfirmation from './ProductionDeleteConfirmation'
import { getSession } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import { getAnimalProductionHistory, getProductionTypes } from '../production.service'
import type { ProductionRecord, ProductionType } from '../types'
import './ProductionHistory.css'
import ProductionCharts from '../../animals/components/ProductionCharts'

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'data'; history: ProductionRecord[]; types: ProductionType[]; catalogError: string | null }

const timestampFormatter = new Intl.DateTimeFormat('es-MX', {
  timeZone: 'UTC', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

function formatTimestamp(timestamp: string): string {
  const instant = new Date(timestamp)
  return Number.isNaN(instant.getTime()) ? timestamp : timestampFormatter.format(instant)
}

function ProductionHistory({ animalId }: { animalId: string }) {
  return <AnimalProductionHistory key={animalId} animalId={animalId} />
}

function AnimalProductionHistory({ animalId }: { animalId: string }) {
  const [attempt, setAttempt] = useState(0)
  const [saved, setSaved] = useState<'created' | 'updated' | 'deleted' | null>(null)
  return <section className="production-history" aria-label="Producción">
    <h2>Producción</h2>
    <WriteOnly><ProductionForm animalId={animalId} onSaved={() => {
      setSaved('created')
      setAttempt((value) => value + 1)
    }} /></WriteOnly>
    {saved === 'updated' && <p role="status">Producción actualizada correctamente.</p>}
    {saved === 'deleted' && <p role="status">Producción eliminada correctamente. El registro dejará de aparecer en el historial.</p>}
    <LoadedHistory key={attempt} animalId={animalId} saved={saved} onRetry={() => setAttempt((value) => value + 1)} onUpdated={() => {
      setSaved('updated')
      setAttempt((value) => value + 1)
    }} onDeleted={() => {
      setSaved('deleted')
      setAttempt((value) => value + 1)
    }} />
  </section>
}

function LoadedHistory({ animalId, saved, onRetry, onUpdated, onDeleted }: {
  animalId: string; saved: 'created' | 'updated' | 'deleted' | null; onRetry: () => void; onUpdated: () => void; onDeleted: () => void
}) {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [editing, setEditing] = useState<ProductionRecord | null>(null)
  const [deleting, setDeleting] = useState<ProductionRecord | null>(null)
  const actionsDisabled = editing !== null || deleting !== null

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      const session = getSession()
      if (!session) { setState({ status: 'error', message: 'No hay una sesión activa.' }); return }
      const [history, types] = await Promise.allSettled([
        getAnimalProductionHistory(animalId, session.access, controller.signal),
        getProductionTypes(session.access, controller.signal),
      ])
      if (controller.signal.aborted) return
      if (history.status === 'rejected') {
        setState({ status: 'error', message: history.reason instanceof ApiError && history.reason.status === 404
          ? 'El historial de producción no está disponible o no fue encontrado.'
          : normalizeApiError(history.reason, 'No fue posible cargar el historial de producción.').message })
        return
      }
      if (!Array.isArray(history.value) || history.value.some(record => !record || record.animal_id !== animalId
        || typeof record.recorded_at !== 'string' || typeof record.quantity !== 'string' || typeof record.unit !== 'string' || typeof record.notes !== 'string')) {
        setState({ status: 'error', message: 'Los registros de producción no corresponden al animal solicitado.' })
        return
      }
      setState({ status: 'data', history: history.value,
        types: types.status === 'fulfilled' ? types.value : [],
        catalogError: types.status === 'rejected'
          ? normalizeApiError(types.reason, 'No fue posible cargar los tipos de producción.').message : null,
      })
    }
    void load()
    return () => controller.abort()
  }, [animalId])

  if (state.status === 'loading') return <p role="status">Cargando producción...</p>
  if (state.status === 'error') return <div><p role="alert">{saved && `El registro fue ${saved === 'deleted' ? 'eliminado' : saved === 'updated' ? 'actualizado' : 'creado'}, pero el historial no pudo actualizarse. `}{state.message}</p><button type="button" onClick={onRetry}>Reintentar consulta del historial</button></div>
  const typeNames = new Map(state.types.map((type) => [type.id, type.name]))
  return <>
    {editing && <WriteOnly><ProductionForm key={editing.id} animalId={animalId} record={editing} onSaved={onUpdated} onCancel={() => setEditing(null)} onRecheck={onRetry} /></WriteOnly>}
    {deleting && <WriteOnly><ProductionDeleteConfirmation key={deleting.id} record={deleting}
      typeName={typeNames.get(deleting.production_type_id) ?? 'Tipo no disponible'} timestamp={formatTimestamp(deleting.recorded_at)}
      onCancel={() => setDeleting(null)} onDeleted={onDeleted} onRecheck={onRetry} /></WriteOnly>}
    {editing && <p>Termina o cancela la edición antes de eliminar un registro.</p>}
    {state.catalogError && <div><p role="alert">{state.catalogError} Los registros conservan su cantidad y unidad almacenada.</p><button type="button" disabled={deleting !== null} onClick={onRetry}>Reintentar consulta</button></div>}
    {state.history.length === 0 ? <p>Este animal todavía no tiene registros de producción.</p> : <>
      <p>Fechas y horas en UTC.</p>
      <ProductionCharts records={state.history} types={state.types} />
      <div className="production-history__table-wrapper">
        <table className="expedient-records" role="table">
          <caption>Historial de producción del animal</caption>
          <thead><tr><th scope="col">Fecha/hora (UTC)</th><th scope="col">Tipo de producción</th><th scope="col">Cantidad</th><th scope="col">Unidad</th><th scope="col">Notas</th><WriteOnly><th scope="col">Acciones</th></WriteOnly></tr></thead>
          <tbody role="rowgroup">{[...state.history].sort((a, b) => Date.parse(b.recorded_at) - Date.parse(a.recorded_at)).map((record) => <tr role="row" key={record.id}>
            <td data-label="Fecha/hora (UTC)" role="cell"><time dateTime={record.recorded_at} title={record.recorded_at}>{formatTimestamp(record.recorded_at)}</time></td>
            <td data-label="Tipo de producción" role="cell">{typeNames.get(record.production_type_id) ?? 'Tipo no disponible'}</td>
            <td data-label="Cantidad" role="cell">{record.quantity}</td><td data-label="Unidad" role="cell">{record.unit}</td><td data-label="Notas" role="cell" className="production-history__notes">{record.notes.trim() || '—'}</td>
            <WriteOnly><td data-label="Acciones" role="cell"><button type="button" disabled={actionsDisabled} onClick={() => {
              if (actionsDisabled) return
              setEditing(record)
            }}>Editar</button>
              <button type="button" disabled={actionsDisabled} onClick={() => {
                if (actionsDisabled) return
                setDeleting(record)
              }}>Eliminar</button></td></WriteOnly>
          </tr>)}</tbody>
        </table>
      </div>
    </>}
  </>
}

export default ProductionHistory
