import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import WriteOnly from '../auth/WriteOnly'
import SoftDeleteAction from '../components/SoftDeleteAction'
import LotList from '../lots/components/LotList'

import { getSession } from '../auth/session'
import { deleteFarm, getFarm } from '../farms/farms.service'
import type { Farm } from '../farms/types'
import { ApiError } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import '../farms/farms.css'

function FarmDetailPage() {
  const { farmId } = useParams<{ farmId: string }>()
  // Remount before rendering another ID, as in AnimalDetailPage (F8-H1).
  return <FarmDetail key={farmId} farmId={farmId} />
}

function FarmDetail({ farmId }: { farmId: string | undefined }) {
  const [attempt, setAttempt] = useState(0)
  return (
    <section className="farms-page">
      <Link className="farms-back" to="/farms">← Volver a fincas</Link>
      <h1>Detalle de finca</h1>
      <FarmInformation key={attempt} farmId={farmId} onRetry={() => setAttempt((value) => value + 1)} />
    </section>
  )
}

function FarmInformation({ farmId, onRetry }: { farmId: string | undefined; onRetry: () => void }) {
  const [farm, setFarm] = useState<Farm | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<{ message: string; retry: boolean } | null>(null)

  useEffect(() => {
    let isActive = true
    async function load() {
      try {
        const session = getSession()
        if (!session || !farmId) throw new Error('Sesión o identificador no disponible.')
        const data = await getFarm(farmId, session.access)
        if (isActive) setFarm(data)
      } catch (cause) {
        if (isActive) {
          const notFound = cause instanceof ApiError && cause.status === 404
          setError({
            message: notFound ? 'La finca no fue encontrada o no está disponible.' : normalizeApiError(cause, 'No fue posible cargar la finca. Intenta de nuevo.').message,
            retry: !(cause instanceof ApiError) || cause.status >= 500,
          })
        }
      } finally {
        if (isActive) setIsLoading(false)
      }
    }
    void load()
    return () => { isActive = false }
  }, [farmId])

  if (isLoading) return <p role="status">Cargando finca...</p>
  if (error) return <div><p role="alert">{error.message}</p>{error.retry && <button type="button" onClick={onRetry}>Reintentar</button>}</div>
  if (!farm) return <p>No hay información disponible de la finca.</p>

  const fields = [
    ['Código', farm.code], ['Nombre', farm.name], ['Tipo', farm.farm_type],
    ['Descripción', farm.description], ['Dirección', farm.address],
    ['Ciudad', farm.city], ['Estado', farm.state], ['País', farm.country],
  ]
  return <><WriteOnly><Link to={`/farms/${farm.id}/edit`}>Editar</Link><SoftDeleteAction key={farm.id} resource="finca" id={farm.id} code={farm.code} name={farm.name} deleteResource={deleteFarm} /></WriteOnly><dl className="farms-detail">{fields.map(([label, value]) => (
    <div key={label}><dt>{label}</dt><dd>{value.trim() || '—'}</dd></div>
  ))}</dl><section className="farm-lots" aria-label="Lotes de la finca"><h2>Lotes</h2><WriteOnly><Link to={`/farms/${farm.id}/lots/new`}>Nuevo lote</Link></WriteOnly><LotList farm={farm} /></section></>
}

export default FarmDetailPage
