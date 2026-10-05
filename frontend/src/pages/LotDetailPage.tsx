import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import WriteOnly from '../auth/WriteOnly'
import SoftDeleteAction from '../components/SoftDeleteAction'
import { getSession } from '../auth/session'
import { getFarms } from '../farms/farms.service'
import type { Farm } from '../farms/types'
import { ApiError } from '../lib/api'
import { normalizeApiError } from '../lib/api-errors'
import FarmReference from '../lots/components/FarmReference'
import { deleteLot, getLot } from '../lots/lots.service'
import type { Lot } from '../lots/types'
import '../lots/lots.css'

function LotDetailPage() {
  const { lotId } = useParams<{ lotId: string }>()
  return <LotDetail key={lotId} lotId={lotId} />
}

function LotDetail({ lotId }: { lotId: string | undefined }) {
  const [attempt, setAttempt] = useState(0)
  return <section className="lots-page"><Link to="/lots">← Volver a lotes</Link><h1>Detalle de lote</h1><LotInformation key={attempt} lotId={lotId} onRetry={() => setAttempt((value) => value + 1)} /></section>
}

function LotInformation({ lotId, onRetry }: { lotId: string | undefined; onRetry: () => void }) {
  const [lot, setLot] = useState<Lot | null>(null)
  const [farms, setFarms] = useState<ReadonlyMap<string, Farm>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<{ message: string; retry: boolean } | null>(null)
  useEffect(() => {
    let active = true
    async function load() {
      let readingLot = true
      try {
        const session = getSession()
        if (!session || !lotId) throw new Error('Sesión o identificador no disponible.')
        // Resolve the lot first so a farm-list failure cannot mask its resource 404.
        const lotData = await getLot(lotId, session.access)
        readingLot = false
        if (!active) return
        const farmData = await getFarms(session.access)
        if (active) {
          setLot(lotData)
          setFarms(new Map(farmData.map((farm) => [farm.id, farm])))
        }
      } catch (cause) {
        if (active) setError({
          message: readingLot && cause instanceof ApiError && cause.status === 404 ? 'El lote no fue encontrado o no está disponible.' : normalizeApiError(cause, 'No fue posible cargar el lote. Intenta de nuevo.').message,
          retry: !(cause instanceof ApiError) || cause.status >= 500,
        })
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => { active = false }
  }, [lotId])
  if (loading) return <p role="status">Cargando lote...</p>
  if (error) return <div><p role="alert">{error.message}</p>{error.retry && <button type="button" onClick={onRetry}>Reintentar</button>}</div>
  if (!lot) return <p>No hay información disponible del lote.</p>
  return <><WriteOnly><Link to={`/lots/${lot.id}/edit`}>Editar</Link><SoftDeleteAction key={lot.id} resource="lote" id={lot.id} code={lot.code} name={lot.name} deleteResource={deleteLot} /></WriteOnly><dl className="lots-detail">
    <div><dt>Código</dt><dd>{lot.code.trim() || '—'}</dd></div>
    <div><dt>Nombre</dt><dd>{lot.name.trim() || '—'}</dd></div>
    <div><dt>Descripción</dt><dd>{lot.description.trim() || '—'}</dd></div>
    <div><dt>Capacidad</dt><dd>{lot.capacity}</dd></div>
    <div><dt>Finca</dt><dd><FarmReference farmId={lot.farm_id} farms={farms} /></dd></div>
  </dl></>
}

export default LotDetailPage
