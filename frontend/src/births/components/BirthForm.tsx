import FieldError from '../../components/FieldError'
import { fieldErrorAttributes } from '../../lib/api-errors'
import { useMemo, useState } from 'react'
import './BirthForm.css'
import type { Animal, Gender } from '../../animals/types'
import type { BreedingEvent } from '../../breeding/types'
import type { PregnancyRecord } from '../../pregnancy/types'
import type { BirthCreatePayload } from '../types'

interface BirthFormProps {
  animal: Animal
  pregnancies: PregnancyRecord[]
  breedings: BreedingEvent[]
  animals: Animal[]
  genders: Gender[]
  disabled: boolean
  fieldErrors: Record<string, string[]>
  onClearErrors: () => void
  onCreate: (payload: BirthCreatePayload) => Promise<boolean>
}

type CalfMode = 'new' | 'existing'

function formatDate(value: string): string {
  return value.split('-').reverse().join('/')
}

function animalLabel(animal: Animal): string {
  return (
    [animal.name?.trim(), animal.internal_id?.trim()]
      .filter(Boolean)
      .join(' · ') ||
    'Animal sin identificación'
  )
}

function BirthForm({
  animal,
  pregnancies,
  breedings,
  animals,
  genders,
  disabled,
  onCreate,
  fieldErrors,
  onClearErrors,
}: BirthFormProps) {
  const [pregnancyId, setPregnancyId] = useState('')
  const [birthDate, setBirthDate] = useState('')
  const [birthWeight, setBirthWeight] = useState('')
  const [alive, setAlive] = useState(true)
  const [dystocia, setDystocia] = useState(false)
  const [notes, setNotes] = useState('')

  const [calfMode, setCalfMode] = useState<CalfMode>('new')
  const [calfId, setCalfId] = useState('')
  const [calfGenderId, setCalfGenderId] = useState('')

  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const pregnancyLabels = useMemo(() => {
    const breedingMap = new Map(
      breedings.map((event) => [event.id, event]),
    )

    return new Map(
      pregnancies.map((pregnancy) => {
        const breeding = breedingMap.get(
          pregnancy.breeding_id,
        )

        const breedingDate = breeding
          ? formatDate(breeding.date)
          : 'Fecha no disponible'

        return [
          pregnancy.id,
          `${breedingDate} · Diagnóstico ${formatDate(pregnancy.diagnosis_date)}`,
        ]
      }),
    )
  }, [pregnancies, breedings])

  const selectedPregnancy = pregnancies.find(
    (pregnancy) => pregnancy.id === pregnancyId,
  )

  const selectedBreeding = selectedPregnancy
    ? breedings.find(
        (event) =>
          event.id === selectedPregnancy.breeding_id,
      )
    : undefined

  const minimumBirthDate = useMemo(() => {
    if (!selectedPregnancy) {
      return ''
    }

    const dates = [
      selectedPregnancy.diagnosis_date,
      selectedBreeding?.date,
    ].filter(Boolean) as string[]

    return dates.sort().at(-1) ?? ''
  }, [selectedPregnancy, selectedBreeding])

  const today = new Date()
    .toISOString()
    .slice(0, 10)

  const availableCalves = useMemo(() => {
    return animals.filter(
      (candidate) =>
        candidate.id !== animal.id &&
        candidate.is_active &&
        (candidate.mother_id === null || candidate.mother_id === animal.id),
    )
  }, [animals, animal.id])

  const [dateContext, setDateContext] = useState({
    pregnancyId, pregnancies, breedings, today,
  })

  // Adjust only when the selection or its source data changes, not while typing.
  // A conditional render adjustment avoids committing a date from the old context.
  if (dateContext.pregnancyId !== pregnancyId ||
      dateContext.pregnancies !== pregnancies ||
      dateContext.breedings !== breedings || dateContext.today !== today) {
    setDateContext({ pregnancyId, pregnancies, breedings, today })
    const nextDate = !selectedPregnancy ? ''
      : !birthDate || birthDate < minimumBirthDate ? minimumBirthDate
      : birthDate > today ? today : birthDate
    if (nextDate !== birthDate) setBirthDate(nextDate)
  }

  function resetForm() {
    setPregnancyId('')
    setBirthDate('')
    setBirthWeight('')
    setAlive(true)
    setDystocia(false)
    setNotes('')
    setCalfMode('new')
    setCalfId('')
    setCalfGenderId('')
    setError(null)
  }

  async function handleSubmit(
    event: React.FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    if (disabled || submitting) {
      return
    }

    setError(null)
    onClearErrors()

    if (!pregnancyId) {
      setError(
        'Debes seleccionar una gestación.',
      )
      return
    }

    if (!selectedPregnancy) {
      setError(
        'La gestación seleccionada ya no está disponible.',
      )
      return
    }

    if (!birthDate) {
      setError(
        'Debes indicar la fecha del parto.',
      )
      return
    }

    if (birthDate < minimumBirthDate) {
      setError(
        'La fecha del parto no puede ser anterior a la reproducción o al diagnóstico de gestación.',
      )
      return
    }

    if (birthDate > today) {
      setError(
        'La fecha del parto no puede estar en el futuro.',
      )
      return
    }

    if (!birthWeight.trim()) {
      setError(
        'Debes indicar el peso al nacimiento.',
      )
      return
    }

    const numericWeight = Number(
      birthWeight.replace(',', '.'),
    )

    if (
      !Number.isFinite(numericWeight) ||
      numericWeight <= 0
    ) {
      setError(
        'El peso al nacimiento debe ser mayor que cero.',
      )
      return
    }

    if (
      calfMode === 'new' &&
      !calfGenderId
    ) {
      setError(
        'Debes indicar el sexo de la nueva cría.',
      )
      return
    }

    if (
      calfMode === 'existing' &&
      !calfId
    ) {
      setError(
        'Debes seleccionar la cría existente.',
      )
      return
    }

    if (calfMode === 'existing' && (!alive ||
        !availableCalves.some((candidate) => candidate.id === calfId))) {
      setError('Selecciona una cría existente disponible únicamente para un parto vivo.')
      return
    }

    const payload: BirthCreatePayload = {
      pregnancy_id: pregnancyId,
      mother_id: animal.id,
      calf_id:
        alive && calfMode === 'existing'
          ? calfId
          : null,
      calf_gender_id:
        calfMode === 'new'
          ? calfGenderId
          : null,
      birth_date: birthDate,
      birth_weight: numericWeight.toFixed(2),
      alive,
      dystocia,
      notes: notes.trim() || null,
    }

    setSubmitting(true)

    try {
      const saved = await onCreate(payload)

      if (saved) {
        resetForm()
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      className="birth-form"
      onSubmit={handleSubmit}
    >
      <h3>Registrar parto</h3>

      {error && (
        <p role="alert">{error}</p>
      )}

      <div className="birth-form__field">
        <label htmlFor="birth-pregnancy">
          Gestación
        </label>

        <select
          id="birth-pregnancy" {...fieldErrorAttributes(fieldErrors, 'pregnancy_id', 'birth-pregnancy')}
          value={pregnancyId}
          onChange={(event) =>
            setPregnancyId(event.target.value)
          }
          disabled={disabled || submitting}
          required
        >
          <option value="">
            Selecciona una gestación
          </option>

          {pregnancies.map((pregnancy) => (
            <option
              key={pregnancy.id}
              value={pregnancy.id}
            >
              {pregnancyLabels.get(
                pregnancy.id,
              ) ?? 'Gestación'}
            </option>
          ))}
        </select>
        <FieldError errors={fieldErrors} field="pregnancy_id" controlId="birth-pregnancy" />
      </div>

      {selectedPregnancy && (
        <div className="birth-form__context">
          <p>
            <strong>Diagnóstico:</strong>{' '}
            {formatDate(
              selectedPregnancy.diagnosis_date,
            )}
          </p>

          {selectedBreeding && (
            <p>
              <strong>Reproducción:</strong>{' '}
              {formatDate(
                selectedBreeding.date,
              )}
            </p>
          )}
        </div>
      )}

      <div className="birth-form__field">
        <label htmlFor="birth-date">
          Fecha del parto
        </label>

        <input
          id="birth-date" {...fieldErrorAttributes(fieldErrors, 'birth_date', 'birth-date')}
          type="date"
          value={birthDate}
          min={minimumBirthDate || undefined}
          max={today}
          onChange={(event) =>
            setBirthDate(event.target.value)
          }
          disabled={
            disabled ||
            submitting ||
            !pregnancyId
          }
          required
        />
        <FieldError errors={fieldErrors} field="birth_date" controlId="birth-date" />
      </div>

      <div className="birth-form__field">
        <label htmlFor="birth-weight">
          Peso al nacimiento (kg)
        </label>

        <input
          id="birth-weight" {...fieldErrorAttributes(fieldErrors, 'birth_weight', 'birth-weight')}
          type="number"
          min="0.01"
          step="0.01"
          value={birthWeight}
          onChange={(event) =>
            setBirthWeight(event.target.value)
          }
          disabled={disabled || submitting}
          required
        />
        <FieldError errors={fieldErrors} field="birth_weight" controlId="birth-weight" />
      </div>

      <fieldset className="birth-form__fieldset">
        <legend>Cría</legend>

        <label>
          <input
            type="radio"
            name="calf-mode"
            value="new"
            checked={calfMode === 'new'}
            onChange={() => {
              setCalfMode('new')
              setCalfId('')
            }}
            disabled={
              disabled || submitting
            }
          />
          Crear nueva cría automáticamente
        </label>

        <label>
          <input
            type="radio"
            name="calf-mode"
            value="existing"
            checked={
              calfMode === 'existing'
            }
            onChange={() => {
              setCalfMode('existing')
              setCalfGenderId('')
            }}
            disabled={
              disabled || submitting || !alive
            }
          />
          Utilizar una cría existente
        </label>
      </fieldset>

      {!alive && <p role="status">
        Un parto no vivo no puede asociar una cría existente. Indica el sexo;
        no se creará un animal automáticamente.
      </p>}

      {calfMode === 'new' ? (
        <div className="birth-form__field">
          <label htmlFor="birth-calf-gender">
            Sexo de la nueva cría
          </label>

          <select
            id="birth-calf-gender" {...fieldErrorAttributes(fieldErrors, 'calf_gender_id', 'birth-calf-gender')}
            value={calfGenderId}
            onChange={(event) =>
              setCalfGenderId(
                event.target.value,
              )
            }
            disabled={
              disabled || submitting
            }
            required
          >
            <option value="">
              Selecciona el sexo
            </option>

            {genders.map((gender) => (
              <option
                key={gender.id}
                value={gender.id}
              >
                {gender.name}
              </option>
            ))}
          </select>
          <FieldError errors={fieldErrors} field="calf_gender_id" controlId="birth-calf-gender" />
        </div>
      ) : (
        <div className="birth-form__field">
          <label htmlFor="birth-calf">
            Cría existente
          </label>

          <select
            id="birth-calf" {...fieldErrorAttributes(fieldErrors, 'calf_id', 'birth-calf')}
            value={calfId}
            onChange={(event) =>
              setCalfId(event.target.value)
            }
            disabled={
              disabled || submitting
            }
            required
          >
            <option value="">
              Selecciona una cría
            </option>

            {availableCalves.map((candidate) => (
              <option
                key={candidate.id}
                value={candidate.id}
              >
                {animalLabel(candidate)}
              </option>
            ))}
          </select>
          <FieldError errors={fieldErrors} field="calf_id" controlId="birth-calf" />
        </div>
      )}

      <label className="birth-form__checkbox">
        <input
          type="checkbox"
          checked={alive}
          onChange={(event) => {
            const nextAlive = event.target.checked
            setAlive(nextAlive)
            if (!nextAlive) {
              setCalfMode('new')
              setCalfId('')
              onClearErrors()
              setError(null)
            }
          }}
          disabled={
            disabled || submitting
          }
        />
        Cría viva
      </label>

      <label className="birth-form__checkbox">
        <input
          type="checkbox"
          checked={dystocia}
          onChange={(event) =>
            setDystocia(
              event.target.checked,
            )
          }
          disabled={
            disabled || submitting
          }
        />
        Distocia
      </label>

      <div className="birth-form__field">
        <label htmlFor="birth-notes">
          Notas
        </label>

        <textarea
          id="birth-notes" {...fieldErrorAttributes(fieldErrors, 'notes', 'birth-notes')}
          value={notes}
          onChange={(event) =>
            setNotes(event.target.value)
          }
          disabled={
            disabled || submitting
          }
          rows={4}
        />
        <FieldError errors={fieldErrors} field="notes" controlId="birth-notes" />
      </div>

      <button
        type="submit"
        disabled={
          disabled ||
          submitting ||
          pregnancies.length === 0
        }
      >
        {submitting
          ? 'Guardando...'
          : 'Registrar parto'}
      </button>
    </form>
  )
}

export default BirthForm
