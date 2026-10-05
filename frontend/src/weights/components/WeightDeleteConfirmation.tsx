import { useEffect, useRef, useState } from 'react'
import { getSession, getSessionRevision } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import { deleteWeight } from '../weights.service'
import type { WeightHistory } from '../types'
import './WeightForm.css'

function WeightDeleteConfirmation({ record, onCancel, onDeleted, onRecheck }: {
  record: WeightHistory
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
      await deleteWeight(record.id, session.access, controller.signal)
      if (current()) onDeleted()
    } catch (cause) {
      if (!current()) return
      const unknownResult = !(cause instanceof ApiError) || cause.status >= 500
      setUncertain(unknownResult)
      setError(unknownResult
        ? 'No se puede confirmar si el servidor procesó la eliminación. Consulta el historial para verificar el estado. No se repetirá DELETE automáticamente.'
        : cause.status === 404
          ? 'El pesaje no existe, no está disponible o ya fue eliminado. No se confirmó esta eliminación; consulta el historial.'
          : cause.status === 401
            ? 'La sesión ya no está disponible. Inicia sesión de nuevo.'
            : normalizeApiError(cause, 'No fue posible eliminar el pesaje.').message)
    } finally {
      if (current()) setSaving(false)
    }
  }

  const date = record.date.split('-').reverse().join('/')
  return <section className="weight-form" aria-label="Confirmar eliminación de pesaje" aria-busy={saving}>
    <h3>Eliminar pesaje</h3>
    <p>Pesaje: {record.id}. Fecha: <time dateTime={record.date}>{date}</time>. Peso: <strong>{record.weight} kg</strong>.</p>
    <p>La eliminación es lógica: el registro permanece almacenado como inactivo y dejará de aparecer en el historial. No existe restauración desde esta interfaz.</p>
    {error && <p role="alert">{error}</p>}
    {saving && <p role="status">Eliminando pesaje...</p>}
    {!uncertain && <button type="button" autoFocus disabled={saving} onClick={() => { if (!saving) onCancel() }}>Cancelar</button>}
    {!attempted && <button type="button" disabled={saving} onClick={() => { void confirmDelete() }}>Confirmar eliminación</button>}
    {attempted && !saving && <button type="button" onClick={onRecheck}>Consultar historial</button>}
  </section>
}

export default WeightDeleteConfirmation
