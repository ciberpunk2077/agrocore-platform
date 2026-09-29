import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getAnimal } from '../animals/animals.service'
import type { Animal } from '../animals/types'
import { getSession } from '../auth/session'
import './AnimalDetailPage.css'
import WeightHistory from '../weights/components/WeightHistory'

function getAnimalIdentification(animal: Animal): string {
  return (
    animal.name?.trim() ||
    animal.internal_id?.trim() ||
    animal.official_tag?.trim() ||
    'Sin identificación'
  )
}

function AnimalDetailPage() {
  const { animalId } = useParams<{ animalId: string }>()

  const [animal, setAnimal] = useState<Animal | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isActive = true

    async function loadAnimal() {
      if (!animalId) {
        if (isActive) {
          setError('No se proporcionó un identificador de animal.')
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
    return <p>No hay información disponible del animal.</p>
  }

  return (
    <section className="animal-detail">
      <Link className="animal-detail__back" to="/animals">
        ← Volver a animales
      </Link>

      <header className="animal-detail__header">
        <div>
          <h1>{getAnimalIdentification(animal)}</h1>
          <p>Información general del animal</p>
        </div>

        <Link
          className="animal-detail__edit"
          to={`/animals/${animal.id}/edit`}
        >
          Editar animal
        </Link>
      </header>

      <div className="animal-detail__card">
        <dl className="animal-detail__grid">
          <div className="animal-detail__field">
            <dt>Especie</dt>
            <dd>{animal.species}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>Raza</dt>
            <dd>{animal.breed}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>Sexo</dt>
            <dd>{animal.gender}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>Estado</dt>
            <dd>{animal.status}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>ID interno</dt>
            <dd>{animal.internal_id?.trim() || '—'}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>Arete oficial</dt>
            <dd>{animal.official_tag?.trim() || '—'}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>Arete electrónico</dt>
            <dd>{animal.electronic_tag?.trim() || '—'}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>Finca</dt>
            <dd>{animal.farm?.trim() || '—'}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>Lote</dt>
            <dd>{animal.lot?.trim() || '—'}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>Fecha de nacimiento</dt>
            <dd>{animal.birth_date || '—'}</dd>
          </div>

          <div className="animal-detail__field">
            <dt>Peso al nacer</dt>
            <dd>
              {animal.birth_weight !== null
                ? `${animal.birth_weight} kg`
                : '—'}
            </dd>
          </div>

          <div className="animal-detail__field animal-detail__notes">
            <dt>Notas</dt>
            <dd>{animal.notes?.trim() || '—'}</dd>
          </div>
        </dl>
      </div>
      <WeightHistory animalId={animal.id} />
    </section>
  )


}

export default AnimalDetailPage