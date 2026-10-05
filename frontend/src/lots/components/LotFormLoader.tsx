import { useEffect, useState } from 'react'
import { getSession } from '../../auth/session'
import { getFarms } from '../../farms/farms.service'
import type { Farm } from '../../farms/types'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import { getLot } from '../lots.service'
import type { Lot } from '../types'
import LotForm from './LotForm'

type Target = { mode: 'create'; id: string } | { mode: 'edit'; id: string }

function LotFormLoader({ target }: { target: Target }) {
  const [attempt, setAttempt] = useState(0)
  return <LoadedLotForm key={attempt} target={target} onRetry={() => setAttempt((value) => value + 1)} />
}

function LoadedLotForm({ target, onRetry }: { target: Target; onRetry: () => void }) {
  const [data, setData] = useState<{ lot?: Lot; farms: Farm[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<{ message: string; retry: boolean } | null>(null)
  const { id, mode } = target
  useEffect(() => {
    let active = true
    async function load() {
      try {
        const session = getSession()
        if (!session) throw new Error('No hay sesión activa.')
        const lot = mode === 'edit' ? await getLot(id, session.access) : undefined
        if (!active) return
        const farms = await getFarms(session.access)
        if (!active) return
        if (mode === 'create' && !farms.some((farm) => farm.id === id)) {
          setError({ message: 'La finca no fue encontrada o no está disponible.', retry: false })
        } else {
          setData({ lot, farms })
        }
      } catch (cause) {
        if (active) setError({
          message: cause instanceof ApiError && cause.status === 404 ? 'El lote o la finca no están disponibles.' : normalizeApiError(cause, 'No fue posible cargar el formulario de lote. Intenta de nuevo.').message,
          retry: !(cause instanceof ApiError) || cause.status >= 500,
        })
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    return () => { active = false }
  }, [id, mode])
  if (loading) return <p role="status">Cargando formulario de lote...</p>
  if (error) return <div><p role="alert">{error.message}</p>{error.retry && <button type="button" onClick={onRetry}>Reintentar</button>}</div>
  return data ? <LotForm lot={data.lot} initialFarmId={id} farms={data.farms} /> : <p>No hay información disponible.</p>
}

export default LotFormLoader
