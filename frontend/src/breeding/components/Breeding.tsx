import WriteOnly from '../../auth/WriteOnly'
import { useEffect, useState } from 'react'

import { getGenders } from '../../animals/animal-options.service'
import { getAnimals } from '../../animals/animals.service'
import type { Animal, Gender } from '../../animals/types'
import { getSession } from '../../auth/session'
import { breedingErrorMessage, getAnimalBreedingHistory, getBreedingTypes } from '../breeding.service'
import type { BreedingEvent, BreedingType } from '../types'
import BreedingForm from './BreedingForm'
import BreedingHistory from './BreedingHistory'

function Breeding({ animal }: { animal: Animal }) {
  return <AnimalBreeding key={animal.id} animal={animal} />
}

function AnimalBreeding({ animal }: { animal: Animal }) {
  const [options, setOptions] = useState<{ types: BreedingType[]; animals: Animal[]; genders: Gender[] } | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  const [optionsAttempt, setOptionsAttempt] = useState(0)
  const [history, setHistory] = useState<BreedingEvent[]>([])
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [historyAttempt, setHistoryAttempt] = useState(0)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let active = true
    async function load() {
      setOptionsError(null)
      const session = getSession()
      if (!session) {
        setOptionsError('No hay una sesión activa.')
        return
      }
      try {
        const [types, animals, genders] = await Promise.all([
          getBreedingTypes(session.access), getAnimals(session.access), getGenders(session.access),
        ])
        if (active) setOptions({ types, animals, genders })
      } catch (cause) {
        if (active) setOptionsError(breedingErrorMessage(cause, 'No fue posible cargar los datos de reproducción.'))
      }
    }
    void load()
    return () => { active = false }
  }, [optionsAttempt])

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setLoadingHistory(true)
      setHistoryError(null)
      const session = getSession()
      if (!session) {
        setHistoryError('No hay una sesión activa.')
        setLoadingHistory(false)
        return
      }
      try {
        const data = await getAnimalBreedingHistory(animal.id, session.access, controller.signal)
        if (!controller.signal.aborted) setHistory(data)
      } catch (cause) {
        if (!controller.signal.aborted) setHistoryError(breedingErrorMessage(cause, 'No fue posible cargar el historial reproductivo.'))
      } finally {
        if (!controller.signal.aborted) setLoadingHistory(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [animal.id, historyAttempt])

  function refreshHistory() {
    setLoadingHistory(true)
    setHistoryAttempt((value) => value + 1)
  }

  const maleGenderId = options?.genders.find((gender) => gender.code === 'M')?.id
  const femaleGenderId = options?.genders.find((gender) => gender.code === 'F')?.id
  const males = options?.animals.filter((candidate) => candidate.is_active && candidate.id !== animal.id
    && candidate.gender_id === maleGenderId) ?? []

  return (
    <section className="breeding" aria-label="Reproducción">
      <h2>Reproducción</h2>
      {optionsError ? <div>
        <p role="alert">{optionsError}</p>
        <button type="button" onClick={() => setOptionsAttempt((value) => value + 1)}>Reintentar carga de datos</button>
      </div> : !options ? <p role="status">Cargando datos de reproducción...</p> : (
        <WriteOnly>{animal.is_active && animal.gender_id === femaleGenderId ? <BreedingForm
          animal={animal} types={options.types} males={males}
          disabled={saved && (loadingHistory || Boolean(historyError))}
          onSaved={() => { setSaved(true); refreshHistory() }}
        /> : <p>El registro de eventos reproductivos está disponible para hembras activas.</p>
      }</WriteOnly>)}
      {saved && <p className="breeding-form__success" role="status">
        El evento reproductivo ya fue guardado correctamente.
        {loadingHistory ? ' Actualizando historial...' : historyError ? ' Reintenta únicamente la consulta del historial antes de registrar otro evento.' : ''}
      </p>}
      {loadingHistory ? <p role="status">Cargando historial reproductivo...</p> : historyError ? <div>
        <p role="alert">{historyError}</p>
        <button type="button" onClick={refreshHistory}>Actualizar historial</button>
      </div> : <BreedingHistory history={history} types={options?.types ?? []} animals={options?.animals ?? []} />}
    </section>
  )
}

export default Breeding
