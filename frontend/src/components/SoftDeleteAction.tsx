import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getSession, getSessionRevision } from '../auth/session'
import { ApiError } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'

interface Props {
  resource: 'finca' | 'lote'
  id: string
  code: string
  name: string
  deleteResource: (id: string, accessToken: string) => Promise<{ success: boolean }>
}

function SoftDeleteAction({ resource, id, code, name, deleteResource }: Props) {
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState(false)
  const [saving, setSaving] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const consumed = useRef(false)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  function openConfirmation() {
    consumed.current = false
    setAttempted(false)
    setError(null)
    setConfirming(true)
  }

  async function confirmDelete() {
    if (consumed.current) return
    consumed.current = true
    setAttempted(true)
    const session = getSession()
    if (!session) { setError('No hay una sesión activa.'); return }
    const revision = getSessionRevision()
    setSaving(true)
    try {
      const result = await deleteResource(id, session.access)
      if (result?.success !== true) throw new Error('Respuesta de baja no confirmada.')
      if (mounted.current && revision === getSessionRevision()) {
        navigate(resource === 'finca' ? '/farms' : '/lots')
      }
    } catch (cause) {
      if (mounted.current && revision === getSessionRevision()) {
        setError(cause instanceof ApiError && cause.status === 404
          ? 'El recurso ya no está disponible o no fue encontrado. No se confirmó la baja.'
          : normalizeApiError(cause, 'No se pudo confirmar la baja. El resultado puede ser incierto por un error de red o servidor. Cancela y comprueba el listado antes de decidir si deseas intentarlo de nuevo.').message)
      }
    } finally {
      if (mounted.current) setSaving(false)
    }
  }

  if (!confirming) return <button type="button" onClick={openConfirmation}>Dar de baja</button>
  return <section aria-label={`Confirmar baja de ${resource}`} aria-busy={saving}>
    <h2>Dar de baja {resource}</h2>
    <p>Código: <strong>{code}</strong>. Nombre: <strong>{name}</strong>.</p>
    {resource === 'finca'
      ? <p>La finca dejará de estar disponible. Sus lotes no serán eliminados automáticamente y seguirán accesibles desde todos los lotes. Animales y movimientos conservan sus referencias. Algunas ubicaciones históricas pueden mostrarse como no disponibles.</p>
      : <p>El lote dejará de estar disponible para nuevas selecciones. Animales y movimientos conservan sus referencias.</p>}
    <p>El código seguirá reservado. No hay restauración disponible desde esta aplicación.</p>
    {error && <p role="alert">{error}</p>}
    {attempted && !saving && <p>Para iniciar otra confirmación, cancela primero. No se reintentará la baja automáticamente.</p>}
    {saving && <p role="status">Procesando baja...</p>}
    <button type="button" autoFocus disabled={saving} onClick={() => setConfirming(false)}>Cancelar</button>
    <button type="button" disabled={saving || attempted} onClick={() => { void confirmDelete() }}>Confirmar baja</button>
  </section>
}

export default SoftDeleteAction
