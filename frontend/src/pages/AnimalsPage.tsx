import { useEffect, useState } from 'react'

import AnimalTable from '../animals/components/AnimalTable'
import { getAnimals } from '../animals/animals.service'
import type { Animal } from '../animals/types'
import { getSession } from '../auth/session'
import './AnimalsPage.css'
import { Link } from 'react-router-dom'

function AnimalsPage() {
  const [animals, setAnimals] = useState<Animal[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isActive = true

    async function loadAnimals() {
      const session = getSession()

      if (!session) {
        if (isActive) {
          setError('No hay una sesión activa.')
          setIsLoading(false)
        }

        return
      }

      try {
        const data = await getAnimals(session.access)

        if (isActive) {
          setAnimals(data)
        }
      } catch {
        if (isActive) {
          setError('No fue posible cargar los animales.')
        }
      } finally {
        if (isActive) {
          setIsLoading(false)
        }
      }
    }

    void loadAnimals()

    return () => {
      isActive = false
    }
  }, [])

  if (isLoading) {
    return <p>Cargando animales...</p>
  }

  if (error) {
    return <p>{error}</p>
  }

  return (
    <section className="animals-page">
      <header className="animals-page__header">
        <h1>Animales</h1>
        <p>Gestión y consulta del inventario ganadero</p>
      </header>
      <Link to="/animals/new">
        Nuevo animal
      </Link>

      {animals.length === 0 ? (
        <p>No hay animales registrados.</p>
      ) : (
        <AnimalTable animals={animals} />
      )}
    </section>
  )
}

export default AnimalsPage