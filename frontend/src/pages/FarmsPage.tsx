import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import WriteOnly from '../auth/WriteOnly'

import { getSession } from '../auth/session'
import { getFarms } from '../farms/farms.service'
import type { Farm } from '../farms/types'
import { normalizeApiError } from '../lib/api-errors'
import '../farms/farms.css'

function FarmsPage() {
  const [attempt, setAttempt] = useState(0)
  return (
    <section className="farms-page">
      <h1>Fincas</h1>
      <Link to="/lots">Ver todos los lotes</Link>
      <WriteOnly><Link to="/farms/new">Nueva finca</Link></WriteOnly>
      <FarmList key={attempt} onRetry={() => setAttempt((value) => value + 1)} />
    </section>
  )
}

function FarmList({ onRetry }: { onRetry: () => void }) {
  const [farms, setFarms] = useState<Farm[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isActive = true
    async function load() {
      try {
        const session = getSession()
        if (!session) throw new Error('No hay una sesión activa.')
        const data = await getFarms(session.access)
        if (isActive) setFarms(data)
      } catch (cause) {
        if (isActive) setError(normalizeApiError(cause, 'No fue posible cargar las fincas. Intenta de nuevo.').message)
      } finally {
        if (isActive) setIsLoading(false)
      }
    }
    void load()
    return () => { isActive = false }
  }, [])

  if (isLoading) return <p role="status">Cargando fincas...</p>
  if (error) return <div><p role="alert">{error}</p><button type="button" onClick={onRetry}>Reintentar</button></div>
  if (!farms.length) return <p>No hay fincas registradas.</p>

  return (
    <div className="farms-table-wrapper">
      <table className="farms-table">
        <caption className="farms-table__caption">Fincas disponibles</caption>
        <thead><tr>{['Código', 'Nombre', 'Tipo', 'Ciudad', 'Estado'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
        <tbody>{farms.map((farm) => (
          <tr key={farm.id}>
            <td>{farm.code.trim() || '—'}</td>
            <td><Link to={`/farms/${farm.id}`}>{farm.name.trim() || '—'}</Link></td>
            <td>{farm.farm_type.trim() || '—'}</td>
            <td>{farm.city.trim() || '—'}</td>
            <td>{farm.state.trim() || '—'}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}

export default FarmsPage
