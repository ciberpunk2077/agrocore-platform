import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import AnimalForm from '../animals/components/form/AnimalForm'
import { getAnimal } from '../animals/animals.service'
import type { Animal } from '../animals/types'
import { getSession } from '../auth/session'

function EditAnimalPage() {
  const { animalId } = useParams<{ animalId: string }>()

  const [animal, setAnimal] = useState<Animal | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isActive = true

    async function loadAnimal() {
      if (!animalId) {
        if (isActive) {
          setError('No se encontró el identificador del animal.')
          setIsLoading(false)
        }

        return
      }

      const session = getSession()

      if (!session) {
        if (isActive) {
          setError('No hay una sesión activa.')
          setIsLoading(false)
        }

        return
      }

      try {
        const data = await getAnimal(animalId, session.access)

        if (isActive) {
          setAnimal(data)
        }
      } catch {
        if (isActive) {
          setError('No fue posible cargar el animal.')
        }
      } finally {
        if (isActive) {
          setIsLoading(false)
        }
      }
    }

    void loadAnimal()

    return () => {
      isActive = false
    }
  }, [animalId])

  if (isLoading) {
    return <p>Cargando animal...</p>
  }

  if (error) {
    return <p>{error}</p>
  }

  if (!animal) {
    return <p>Animal no encontrado.</p>
  }

  return (
    <section>
      <Link to={`/animals/${animal.id}`}>← Volver al animal</Link>

      <h1>Editar animal</h1>

      <p>
        Actualiza la información de{' '}
        <strong>
          {animal.name || animal.internal_id || 'Sin identificación'}
        </strong>
        .
      </p>

      <AnimalForm animal={animal} />
    </section>
  )
}

export default EditAnimalPage