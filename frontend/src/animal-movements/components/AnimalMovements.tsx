import { useEffect, useState } from 'react'

import { getFarms, getLots } from '../../animals/animal-options.service'
import { getAnimal } from '../../animals/animals.service'
import type { Animal, Farm, Lot } from '../../animals/types'
import { getSession } from '../../auth/session'
import { getAnimalMovementHistory, getMovementTypes } from '../animal-movements.service'
import type { AnimalMovement, MovementType } from '../types'
import AnimalMovementForm from './AnimalMovementForm'
import AnimalMovementHistory from './AnimalMovementHistory'

interface AnimalMovementsProps {
  animalId: string
  animal: Animal
  onAnimalUpdated: (animal: Animal) => void
}

function AnimalMovements({ animalId, animal, onAnimalUpdated }: AnimalMovementsProps) {
  const [types, setTypes] = useState<MovementType[]>([])
  const [farms, setFarms] = useState<Farm[]>([])
  const [lots, setLots] = useState<Lot[]>([])
  const [history, setHistory] = useState<AnimalMovement[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let isActive = true

    async function load() {
      setIsLoading(true)
      setError(null)
      const session = getSession()
      if (!session) {
        setError('No hay una sesión activa.')
        setIsLoading(false)
        return
      }
      try {
        const [[movementTypes, farmData, lotData], movements] = await Promise.all([
          Promise.all([
            getMovementTypes(session.access),
            getFarms(session.access),
            getLots(session.access),
          ]).catch(() => { throw new Error('No fue posible cargar los catálogos de movimientos.') }),
          getAnimalMovementHistory(animalId, session.access)
            .catch(() => { throw new Error('No fue posible cargar el historial de movimientos.') }),
        ])
        if (isActive) {
          setTypes(movementTypes)
          setFarms(farmData)
          setLots(lotData)
          setHistory(movements)
        }
      } catch (cause) {
        if (isActive) setError(cause instanceof Error ? cause.message : 'No fue posible cargar los movimientos.')
      } finally {
        if (isActive) setIsLoading(false)
      }
    }
    void load()
    return () => { isActive = false }
  }, [animalId, attempt])

  async function refresh(saved?: AnimalMovement) {
    if (saved) setHistory((items) => [saved, ...items])
    setIsRefreshing(true)
    try {
      const session = getSession()
      if (!session) throw new Error('No session')
      const [movements, updatedAnimal] = await Promise.all([
        getAnimalMovementHistory(animalId, session.access),
        getAnimal(animalId, session.access),
      ])
      setHistory(movements)
      onAnimalUpdated(updatedAnimal)
      setRefreshError(null)
    } catch {
      setRefreshError('El movimiento se guardó, pero no fue posible actualizar el historial y los datos del animal. Reintenta la actualización antes de registrar otro movimiento.')
    } finally {
      setIsRefreshing(false)
    }
  }

  const lastDate = history.reduce((latest, item) => item.date > latest ? item.date : latest, '')

  return (
    <section className="animal-movements" aria-label="Movimientos">
      <h2>Movimientos</h2>
      {isLoading ? <p role="status">Cargando movimientos...</p> : error ? (
        <div>
          <p role="alert">{error}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}>Reintentar</button>
        </div>
      ) : (
        <>
          {refreshError && (
            <div>
              <p role="alert">{refreshError}</p>
              <button type="button" disabled={isRefreshing} onClick={() => void refresh()}>
                {isRefreshing ? 'Actualizando...' : 'Actualizar datos'}
              </button>
            </div>
          )}
          <AnimalMovementForm
            animalId={animalId} animal={animal} types={types} farms={farms} lots={lots}
            lastDate={lastDate} disabled={isRefreshing || Boolean(refreshError)} onSaved={refresh}
          />
          <AnimalMovementHistory history={history} types={types} farms={farms} lots={lots} />
        </>
      )}
    </section>
  )
}

export default AnimalMovements
