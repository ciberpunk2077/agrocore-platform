import { useEffect, useRef, useState } from 'react'
import { getSession, getSessionRevision } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import { deleteProduction } from '../production.service'
import type { ProductionRecord } from '../types'

function ProductionDeleteConfirmation({ record, typeName, timestamp, onCancel, onDeleted, onRecheck }: {
  record: ProductionRecord; typeName: string; timestamp: string
  onCancel: () => void; onDeleted: () => void; onRecheck: () => void
}) {
  const [saving, setSaving] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uncertain, setUncertain] = useState(false)
  const consumed = useRef(false)
  const lifetime = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    return () => { controller.abort(); lifetime.current = null }
  }, [])

  async function confirmDelete() {
    const controller = lifetime.current
    if (consumed.current || !controller || controller.signal.aborted) return
    consumed.current = true
    setAttempted(true)
    const session = getSession()
    if (!session) { setError('No hay una sesión activa.'); return }
    const revision = getSessionRevision()
    const current = () => !controller.signal.aborted && revision === getSessionRevision()
    setSaving(true)
    try {
      const result = await deleteProduction(record.id, session.access, controller.signal)
      if (result?.success !== true) throw new Error('Eliminación no confirmada.')
      if (current()) onDeleted()
    } catch (cause) {
      if (!current()) return
      const unknownResult = !(cause instanceof ApiError) || cause.status >= 500
      setUncertain(unknownResult)
      setError(unknownResult
        ? 'No se puede confirmar el resultado de la eliminación. Consulta el historial para verificar el estado. No se repetirá DELETE automáticamente.'
        : cause instanceof ApiError && cause.status === 404
          ? 'El registro no existe, no está disponible o ya fue eliminado. No se confirmó esta eliminación; consulta el historial.'
          : normalizeApiError(cause, 'No fue posible eliminar el registro.').message)
    } finally {
      if (!controller.signal.aborted) setSaving(false)
    }
  }

  return <section className="production-form" aria-label="Confirmar eliminación de producción" aria-busy={saving}>
    <h3>Eliminar registro de producción</h3>
    <p>Tipo: <strong>{typeName}</strong>. Fecha/hora (UTC): <time dateTime={record.recorded_at}>{timestamp}</time>.
      Cantidad: <strong>{record.quantity} {record.unit}</strong>.</p>
    <p>Registro: {record.id}</p>
    <p>Dejará de aparecer en el historial. La eliminación es lógica: el registro permanece almacenado como inactivo. No existe restauración desde la aplicación.</p>
    {error && <p role="alert">{error}</p>}
    {saving && <p role="status">Eliminando producción...</p>}
    {!uncertain && <button type="button" autoFocus disabled={saving} onClick={onCancel}>Cancelar</button>}
    {!attempted && <button type="button" disabled={saving} onClick={() => { void confirmDelete() }}>Eliminar</button>}
    {attempted && !saving && <button type="button" onClick={onRecheck}>Consultar historial</button>}
  </section>
}

export default ProductionDeleteConfirmation
