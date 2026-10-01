import { useEffect, useRef, useState } from 'react'

import { getAnimals } from '../../animals/animals.service'
import { getGenders } from '../../animals/animal-options.service'
import type { Animal, Gender } from '../../animals/types'
import { getSession } from '../../auth/session'
import { getAnimalBreedingHistory } from '../../breeding/breeding.service'
import type { BreedingEvent } from '../../breeding/types'
import { getAnimalPregnancyHistory } from '../../pregnancy/pregnancy.service'
import type { PregnancyRecord } from '../../pregnancy/types'
import {
  birthErrorMessage,
  createBirth,
  getAnimalBirthHistory,
} from '../births.service'
import type { BirthCreatePayload, BirthRecord } from '../types'
import BirthForm from './BirthForm'
import BirthHistory from './BirthHistory'

interface BirthData {
  pregnancies: PregnancyRecord[]
  breedings: BreedingEvent[]
  history: BirthRecord[]
  animals: Animal[]
  genders: Gender[]
}

function Births({ animal }: { animal: Animal }) {
  return <AnimalBirths key={animal.id} animal={animal} />
}

function AnimalBirths({ animal }: { animal: Animal }) {
  const [data, setData] = useState<BirthData | null>(null)
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
        const [
          pregnancies,
          breedings,
          history,
          animals,
          genders,
        ] = await Promise.all([
          getAnimalPregnancyHistory(
            animal.id,
            session.access,
            controller.signal,
          ),
          getAnimalBreedingHistory(
            animal.id,
            session.access,
            controller.signal,
          ),
          getAnimalBirthHistory(
            animal.id,
            session.access,
            controller.signal,
          ),
          getAnimals(session.access),
          getGenders(session.access),
        ])

        if (!controller.signal.aborted) {
          setData({
            pregnancies,
            breedings,
            history,
            animals,
            genders,
          })
        }
      } catch (cause) {
        if (!controller.signal.aborted) {
          setLoadError(
            birthErrorMessage(
              cause,
              'No fue posible cargar los datos de partos.',
            ),
          )
        }
      }
    }

    void load()

    return () => controller.abort()
  }, [animal.id, attempt])

  async function synchronize() {
    if (!active.current || refreshing.current) {
      return
    }

    refreshing.current = true
    locked.current = true

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

      const [
        history,
        pregnancies,
        animals,
      ] = await Promise.all([
        getAnimalBirthHistory(
          animal.id,
          session.access,
          controller.signal,
        ),
        getAnimalPregnancyHistory(
          animal.id,
          session.access,
          controller.signal,
        ),
        getAnimals(
          session.access,
        ),
      ])

      if (
        !controller.signal.aborted &&
        active.current
      ) {
        setData((current) =>
          current
            ? {
                ...current,
                history,
                pregnancies,
                animals,
              }
            : current,
        )

        locked.current = false
      }
    } catch (cause) {
      if (
        !controller.signal.aborted &&
        active.current
      ) {
        setSyncError(
          birthErrorMessage(
            cause,
            'No fue posible actualizar los datos de partos.',
          ),
        )
      }
    } finally {
      refreshing.current = false

      if (
        !controller.signal.aborted &&
        active.current
      ) {
        setBusy(false)
      }
    }
  }

  async function handleCreate(
    payload: BirthCreatePayload,
  ): Promise<boolean> {
    if (
      !active.current ||
      locked.current ||
      !data
    ) {
      return false
    }

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

    try {
      const saved = await createBirth(
        payload,
        session.access,
      )

      if (!active.current) {
        return false
      }

      setData((current) =>
        current
          ? {
              ...current,
              history: [
                saved,
                ...current.history,
              ],
              pregnancies: current.pregnancies.map(
                (pregnancy) =>
                  pregnancy.id === saved.pregnancy_id
                    ? {
                        ...pregnancy,
                        status: 'FINISHED',
                      }
                    : pregnancy,
              ),
            }
          : current,
      )

      setSuccess(
        'El parto ya fue registrado correctamente.',
      )

      void synchronize()

      return true
    } catch (cause) {
      if (active.current) {
        setError(
          birthErrorMessage(
            cause,
            'No fue posible registrar el parto. Revisa los datos e intenta de nuevo.',
          ),
        )

        locked.current = false
        setBusy(false)
      }

      return false
    }
  }

  const availablePregnancies =
    data?.pregnancies.filter(
      (pregnancy) =>
        pregnancy.animal_id === animal.id &&
        pregnancy.status === 'ACTIVE' &&
        !data.history.some(
          (birth) =>
            birth.pregnancy_id === pregnancy.id,
        ),
    ) ?? []

  return (
    <section
      className="births"
      aria-label="Partos"
    >
      <h2>Partos</h2>

      {!data ? (
        loadError ? (
          <div>
            <p role="alert">{loadError}</p>

            <button
              type="button"
              onClick={() =>
                setAttempt((value) => value + 1)
              }
            >
              Reintentar
            </button>
          </div>
        ) : (
          <p role="status">
            Cargando datos de partos...
          </p>
        )
      ) : (
        <>
          {success && (
            <p
              className="birth-form__success"
              role="status"
            >
              {success}
            </p>
          )}

          {error && (
            <p role="alert">{error}</p>
          )}

          {busy && (
            <p role="status">
              Procesando y actualizando datos...
            </p>
          )}

          {syncError && (
            <div>
              <p role="alert">
                {syncError}
              </p>

              <p>
                Actualiza los datos antes de
                registrar otro parto. Reintentar
                solo consulta los datos; no repite
                el guardado.
              </p>

              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void synchronize()
                }
              >
                Reintentar
              </button>
            </div>
          )}

          <BirthForm
            animal={animal}
            pregnancies={availablePregnancies}
            breedings={data.breedings}
            animals={data.animals}
            genders={data.genders}
            disabled={
              busy ||
              Boolean(syncError) ||
              !animal.is_active
            }
            onCreate={handleCreate}
          />

          <BirthHistory
            history={data.history}
            animals={data.animals}
            genders={data.genders}
            disabled={
              busy ||
              Boolean(syncError)
            }
          />
        </>
      )}
    </section>
  )
}

export default Births