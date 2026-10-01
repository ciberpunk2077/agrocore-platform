import { useEffect, useRef, useState } from 'react'

import { getAnimals } from '../../animals/animals.service'
import type { Animal } from '../../animals/types'
import { getSession } from '../../auth/session'
import { getAnimalBreedingHistory, getBreedingTypes } from '../../breeding/breeding.service'
import type { BreedingEvent, BreedingType } from '../../breeding/types'
import { abortPregnancy, createPregnancy, getAnimalPregnancyHistory, pregnancyErrorMessage } from '../pregnancy.service'
import type { PregnancyCreatePayload, PregnancyRecord } from '../types'
import PregnancyForm from './PregnancyForm'
import PregnancyHistory from './PregnancyHistory'

interface PregnancyData {
  events: BreedingEvent[]
  history: PregnancyRecord[]
  types: BreedingType[]
  animals: Animal[]
}

function Pregnancy({ animal }: { animal: Animal }) {
  return <AnimalPregnancy key={animal.id} animal={animal} />
}

function AnimalPregnancy({ animal }: { animal: Animal }) {
  const [data, setData] = useState<PregnancyData | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const active = useRef(false)
  const locked = useRef(false)
  const refreshing = useRef(false)
  const refreshController = useRef<AbortController | null>(null)
  const refreshEvents = useRef(false)

  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
      refreshController.current?.abort()
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setLoadError(null)
      const session = getSession()
      if (!session) {
        setLoadError('No hay una sesión activa.')
        return
      }
      try {
        const [events, history, types, animals] = await Promise.all([
          getAnimalBreedingHistory(animal.id, session.access, controller.signal),
          getAnimalPregnancyHistory(animal.id, session.access, controller.signal),
          getBreedingTypes(session.access), getAnimals(session.access),
        ])
        if (!controller.signal.aborted) setData({ events, history, types, animals })
      } catch (cause) {
        if (!controller.signal.aborted) setLoadError(pregnancyErrorMessage(cause, 'No fue posible cargar los datos de gestación.'))
      }
    }
    void load()
    return () => controller.abort()
  }, [animal.id, attempt])

  async function synchronize(includeEvents: boolean) {
    if (!active.current || refreshing.current) return
    refreshing.current = true
    locked.current = true
    refreshEvents.current = includeEvents
    const controller = new AbortController()
    refreshController.current = controller
    setBusy(true)
    setSyncError(null)
    try {
      const session = getSession()
      if (!session) {
        setSyncError('No hay una sesión activa.')
        return
      }
      const [history, events] = await Promise.all([
        getAnimalPregnancyHistory(animal.id, session.access, controller.signal),
        includeEvents ? getAnimalBreedingHistory(animal.id, session.access, controller.signal) : Promise.resolve(null),
      ])
      if (!controller.signal.aborted && active.current) {
        setData((current) => current ? { ...current, history, events: events ?? current.events } : current)
        locked.current = false
      }
    } catch (cause) {
      if (!controller.signal.aborted && active.current) {
        setSyncError(pregnancyErrorMessage(cause, 'No fue posible actualizar los datos de gestación.'))
      }
    } finally {
      refreshing.current = false
      if (!controller.signal.aborted && active.current) setBusy(false)
    }
  }

  async function mutate(operation: (token: string) => Promise<PregnancyRecord>, message: string): Promise<boolean> {
    if (!active.current || locked.current || !data) return false
    locked.current = true
    setBusy(true)
    setError(null)
    setSuccess(null)
    const session = getSession()
    if (!session) {
      setError('No hay una sesión activa.')
      locked.current = false
      setBusy(false)
      return false
    }
    let saved: PregnancyRecord
    try {
      saved = await operation(session.access)
    } catch (cause) {
      if (active.current) {
        setError(pregnancyErrorMessage(cause, 'No fue posible guardar la operación. Revisa los datos e intenta de nuevo.'))
        locked.current = false
        setBusy(false)
      }
      return false
    }
    if (!active.current) return false
    // Reflect an aborted record immediately without changing the server's history order.
    setData((current) => current ? {
      ...current, history: current.history.map((item) => item.id === saved.id ? saved : item),
    } : current)
    setSuccess(message)
    // A successful write is never retried; keep writes locked until the GET succeeds.
    void synchronize(false)
    return true
  }

  const usedEvents = new Set(data?.history.map((item) => item.breeding_id))
  const availableEvents = data?.events.filter((event) => event.animal_id === animal.id && !usedEvents.has(event.id)) ?? []
  const typeNames = new Map(data?.types.map((type) => [type.id, type.name]))
  const animalNames = new Map(data?.animals.map((item) => [item.id,
    [item.name?.trim(), item.internal_id?.trim()].filter(Boolean).join(' · ') || 'Macho sin identificación',
  ]))
  const eventLabels = new Map(data?.events.map((event) => [event.id, [
    event.date.split('-').reverse().join('/'),
    typeNames.get(event.breeding_type_id) ?? 'Tipo no disponible',
    event.male_id ? animalNames.get(event.male_id) ?? 'Macho no disponible' : 'Sin macho',
  ].join(' · ')]))

  function handleCreate(payload: PregnancyCreatePayload) {
    if (payload.animal_id !== animal.id || !availableEvents.some((event) => event.id === payload.breeding_id)) return Promise.resolve(false)
    return mutate((token) => createPregnancy(payload, token), 'La gestación ya fue guardada correctamente.')
  }

  function handleAbort(item: PregnancyRecord) {
    if (locked.current || !active.current || item.status !== 'ACTIVE' || item.animal_id !== animal.id) return
    if (!window.confirm(`¿Registrar el aborto de la gestación diagnosticada el ${item.diagnosis_date.split('-').reverse().join('/')}?`)) return
    void mutate((token) => abortPregnancy(item.id, token), 'El aborto ya fue registrado correctamente.')
  }

  return <section className="pregnancy" aria-label="Gestación">
    <h2>Gestación</h2>
    {!data ? loadError ? <div>
      <p role="alert">{loadError}</p>
      <button type="button" onClick={() => setAttempt((value) => value + 1)}>Reintentar</button>
    </div> : <p role="status">Cargando datos de gestación...</p> : <>
      {success && <p className="pregnancy-form__success" role="status">{success}</p>}
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Procesando y actualizando datos...</p>}
      {syncError && <div>
        <p role="alert">{syncError}</p>
        <p>Actualiza los datos antes de registrar otra operación. Reintentar solo consulta los datos; no repite el guardado.</p>
        <button type="button" disabled={busy} onClick={() => void synchronize(refreshEvents.current)}>Reintentar</button>
      </div>}
      <button type="button" disabled={busy || Boolean(syncError)} onClick={() => {
        if (!locked.current) void synchronize(true)
      }}>Actualizar eventos disponibles</button>
      <PregnancyForm animal={animal} events={availableEvents} eventLabels={eventLabels}
        disabled={busy || Boolean(syncError) || !animal.is_active} onCreate={handleCreate} />
      <PregnancyHistory history={data.history} eventLabels={eventLabels}
        disabled={busy || Boolean(syncError)} onAbort={handleAbort} />
    </>}
  </section>
}

export default Pregnancy
