import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getSession } from '../auth/session'
import FarmForm from '../farms/components/FarmForm'
import { getFarm } from '../farms/farms.service'
import type { Farm } from '../farms/types'
import { ApiError } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import '../farms/farms.css'

function EditFarmPage() {
  const { farmId } = useParams<{ farmId: string }>()
  return <EditFarm key={farmId} farmId={farmId} />
}

function EditFarm({ farmId }: { farmId: string | undefined }) {
  const [attempt, setAttempt] = useState(0)
  return <section className="farms-page"><h1>Editar finca</h1><Link to={farmId ? `/farms/${farmId}` : '/farms'}>← Volver a finca</Link><EditFarmLoader key={attempt} farmId={farmId} onRetry={() => setAttempt((value) => value + 1)} /></section>
}

function EditFarmLoader({ farmId, onRetry }: { farmId: string | undefined; onRetry: () => void }) {
  const [farm, setFarm] = useState<Farm | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<{ message: string; retry: boolean } | null>(null)
  useEffect(() => {
    let active = true
    async function load() {
      try {
        const session = getSession()
        if (!session || !farmId) throw new Error('Sesión o identificador no disponible.')
        const data = await getFarm(farmId, session.access)
        if (active) setFarm(data)
      } catch (cause) {
        if (active) setError({
          message: cause instanceof ApiError && cause.status === 404 ? 'La finca no fue encontrada o no está disponible.' : normalizeApiError(cause, 'No fue posible cargar la finca.').message,
          retry: !(cause instanceof ApiError) || cause.status >= 500,
        })
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => { active = false }
  }, [farmId])
  if (loading) return <p role="status">Cargando finca...</p>
  if (error) return <div><p role="alert">{error.message}</p>{error.retry && <button type="button" onClick={onRetry}>Reintentar</button>}</div>
  return farm ? <FarmForm key={farm.id} farm={farm} /> : <p>No hay información disponible de la finca.</p>
}

export default EditFarmPage
