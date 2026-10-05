import FieldError from '../../../components/FieldError'
import { fieldErrorAttributes, normalizeApiError } from '../../../lib/api-errors'
import {
  type FormEvent,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import { getSession } from '../../../auth/session'
import {
  getAnimalStatuses,
  getBreeds,
  getFarms,
  getGenders,
  getLots,
  getSpecies,
} from '../../animal-options.service'
import { createAnimal, getParentCandidates, updateAnimal, } from '../../animals.service'
import type {
  Animal,
  AnimalParentCandidate,
  AnimalStatus,
  AnimalWritePayload,
  Breed,
  Farm,
  Gender,
  Lot,
  Species,
} from '../../types'

interface AnimalFormProps {
  animal?: Animal
}

function AnimalForm({ animal }: AnimalFormProps) {
  const navigate = useNavigate()

  const [species, setSpecies] = useState<Species[]>([])
  const [breeds, setBreeds] = useState<Breed[]>([])
  const [genders, setGenders] = useState<Gender[]>([])
  const [statuses, setStatuses] = useState<AnimalStatus[]>([])
  const [farms, setFarms] = useState<Farm[]>([])
  const [lots, setLots] = useState<Lot[]>([])
  const [animals, setAnimals] = useState<AnimalParentCandidate[]>([])

  const [internalId, setInternalId] = useState(animal?.internal_id ?? '')
  const [name, setName] = useState(animal?.name ?? '')
  const [officialTag, setOfficialTag] = useState(animal?.official_tag ?? '')
  const [electronicTag, setElectronicTag] = useState(
    animal?.electronic_tag ?? '',
  )

  const [speciesId, setSpeciesId] = useState(animal?.species_id ?? '')
  const [breedId, setBreedId] = useState(animal?.breed_id ?? '')
  const [genderId, setGenderId] = useState(animal?.gender_id ?? '')
  const [statusId, setStatusId] = useState(animal?.status_id ?? '')

  const [farmId, setFarmId] = useState(animal?.farm_id ?? '')
  const [lotId, setLotId] = useState(animal?.lot_id ?? '')

  const [birthDate, setBirthDate] = useState(animal?.birth_date ?? '')
  const [birthWeight, setBirthWeight] = useState(
    animal?.birth_weight ?? '',
  )

  const [motherId, setMotherId] = useState(animal?.mother_id ?? '')
  const [fatherId, setFatherId] = useState(animal?.father_id ?? '')

  const [notes, setNotes] = useState(animal?.notes ?? '')
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  useEffect(() => {
    let isActive = true

    async function loadOptions() {
      const session = getSession()

      if (!session) {
        if (isActive) {
          setError('No hay una sesión activa.')
          setIsLoading(false)
        }

        return
      }

      try {
        const [
          speciesData,
          breedsData,
          gendersData,
          statusesData,
          farmsData,
          lotsData,
          animalsData,
        ] = await Promise.all([
          getSpecies(session.access),
          getBreeds(session.access),
          getGenders(session.access),
          getAnimalStatuses(session.access),
          getFarms(session.access),
          getLots(session.access),
          getParentCandidates(session.access),
        ])

        if (isActive) {
          setSpecies(speciesData)
          setBreeds(breedsData)
          setGenders(gendersData)
          setStatuses(statusesData)
          setFarms(farmsData)
          setLots(lotsData)
          setAnimals(animalsData)
        }
      } catch {
        if (isActive) {
          setError('No fue posible cargar las opciones del formulario.')
        }
      } finally {
        if (isActive) {
          setIsLoading(false)
        }
      }
    }

    void loadOptions()

    return () => {
      isActive = false
    }
  }, [])

  const filteredBreeds = useMemo(
    () => breeds.filter((breed) => breed.species_id === speciesId),
    [breeds, speciesId],
  )

  const filteredLots = useMemo(
    () => lots.filter((lot) => lot.farm_id === farmId),
    [lots, farmId],
  )

  const possibleMothers = useMemo(
    () => animals.filter((candidate) =>
      candidate.id !== animal?.id && candidate.gender_code === 'F'),
    [animal?.id, animals],
  )

  const possibleFathers = useMemo(
    () => animals.filter((candidate) =>
      candidate.id !== animal?.id && candidate.gender_code === 'M'),
    [animal?.id, animals],
  )

  const historicalMother = Boolean(animal?.mother_id && motherId === animal.mother_id &&
    !animals.some((candidate) => candidate.id === animal.mother_id))
  const historicalFather = Boolean(animal?.father_id && fatherId === animal.father_id &&
    !animals.some((candidate) => candidate.id === animal.father_id))

  function parentLabel(parent: AnimalParentCandidate): string {
    const identification = [parent.internal_id?.trim(), parent.name?.trim()]
      .filter(Boolean).join(' · ') || 'Sin identificación'
    return `${identification}${parent.is_active ? '' : ' (Inactivo)'}`
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFieldErrors({})

    const session = getSession()

    if (!session) {
      setError('No hay una sesión activa.')
      return
    }

    setError(null)
    if ((!animal && (!farmId || !lotId)) ||
        Boolean(farmId) !== Boolean(lotId) ||
        (farmId && !filteredLots.some((lot) => lot.id === lotId))) {
      setError('Selecciona una finca y un lote válido, o deja ambos sin ubicación al editar.')
      return
    }
    setIsSubmitting(true)

    const payload: AnimalWritePayload = {
      farm_id: farmId,
      lot_id: lotId,
      species_id: speciesId,
      breed_id: breedId,
      gender_id: genderId,
      status_id: statusId,
      internal_id: internalId.trim(),

      official_tag: officialTag.trim(),
      electronic_tag: electronicTag.trim(),
      name: name.trim(),
      birth_date: birthDate || null,
      birth_weight: birthWeight ? Number(birthWeight) : null,
      mother_id: motherId || null,
      father_id: fatherId || null,
      notes: notes.trim() || null,
    }

    try {
      const savedAnimal = animal
        ? await updateAnimal(animal.id, {
            ...payload, farm_id: farmId || null, lot_id: lotId || null,
          }, session.access)
        : await createAnimal(payload, session.access)

      navigate(`/animals/${savedAnimal.id}`)
    } catch (cause) {
      const normalized = normalizeApiError(cause, animal
        ? 'No fue posible actualizar el animal.'
        : 'No fue posible registrar el animal.')
      setError(normalized.message)
      setFieldErrors(normalized.fieldErrors)
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return <p>Cargando formulario...</p>
  }

  if (error && species.length === 0) {
    return <p>{error}</p>
  }

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label htmlFor="internalId">ID interno</label>
        <input
          id="internalId" {...fieldErrorAttributes(fieldErrors, 'internal_id', 'internalId')}
          type="text"
          value={internalId}
          onChange={(event) => setInternalId(event.target.value)}
          required
        />
        <FieldError errors={fieldErrors} field="internal_id" controlId="internalId" />
      </div>

      <div>
        <label htmlFor="name">Nombre</label>
        <input
          id="name" {...fieldErrorAttributes(fieldErrors, 'name', 'name')}
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <FieldError errors={fieldErrors} field="name" controlId="name" />
      </div>

      <div>
        <label htmlFor="officialTag">Arete oficial</label>
        <input
          id="officialTag" {...fieldErrorAttributes(fieldErrors, 'official_tag', 'officialTag')}
          type="text"
          value={officialTag}
          onChange={(event) => setOfficialTag(event.target.value)}
        />
        <FieldError errors={fieldErrors} field="official_tag" controlId="officialTag" />
      </div>

      <div>
        <label htmlFor="electronicTag">Arete electrónico</label>
        <input
          id="electronicTag" {...fieldErrorAttributes(fieldErrors, 'electronic_tag', 'electronicTag')}
          type="text"
          value={electronicTag}
          onChange={(event) => setElectronicTag(event.target.value)}
        />
        <FieldError errors={fieldErrors} field="electronic_tag" controlId="electronicTag" />
      </div>

      <div>
        <label htmlFor="species">Especie</label>
        <select
          id="species" {...fieldErrorAttributes(fieldErrors, 'species_id', 'species')}
          value={speciesId}
          onChange={(event) => {
            setSpeciesId(event.target.value)
            setBreedId('')
          }}
          required
        >
          <option value="">Selecciona una especie</option>
          {species.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <FieldError errors={fieldErrors} field="species_id" controlId="species" />
      </div>

      <div>
        <label htmlFor="breed">Raza</label>
        <select
          id="breed" {...fieldErrorAttributes(fieldErrors, 'breed_id', 'breed')}
          value={breedId}
          onChange={(event) => setBreedId(event.target.value)}
          disabled={!speciesId}
          required
        >
          <option value="">Selecciona una raza</option>
          {filteredBreeds.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <FieldError errors={fieldErrors} field="breed_id" controlId="breed" />
      </div>

      <div>
        <label htmlFor="gender">Sexo</label>
        <select
          id="gender" {...fieldErrorAttributes(fieldErrors, 'gender_id', 'gender')}
          value={genderId}
          onChange={(event) => setGenderId(event.target.value)}
          required
        >
          <option value="">Selecciona el sexo</option>
          {genders.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <FieldError errors={fieldErrors} field="gender_id" controlId="gender" />
      </div>

      <div>
        <label htmlFor="status">Estado</label>
        <select
          id="status" {...fieldErrorAttributes(fieldErrors, 'status_id', 'status')}
          value={statusId}
          onChange={(event) => setStatusId(event.target.value)}
          required
        >
          <option value="">Selecciona un estado</option>
          {statuses.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <FieldError errors={fieldErrors} field="status_id" controlId="status" />
      </div>

      <div>
        <label htmlFor="farm">Finca</label>
        <select
          id="farm" {...fieldErrorAttributes(fieldErrors, 'farm_id', 'farm')}
          value={farmId}
          onChange={(event) => {
            setFarmId(event.target.value)
            setLotId('')
          }}
          required={!animal}
        >
          <option value="">{animal ? 'Sin ubicación' : 'Selecciona una finca'}</option>
          {farms.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <FieldError errors={fieldErrors} field="farm_id" controlId="farm" />
      </div>

      <div>
        <label htmlFor="lot">Lote</label>
        <select
          id="lot" {...fieldErrorAttributes(fieldErrors, 'lot_id', 'lot')}
          value={lotId}
          onChange={(event) => setLotId(event.target.value)}
          disabled={!farmId}
          required={!animal || Boolean(farmId)}
        >
          <option value="">Selecciona un lote</option>
          {filteredLots.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <FieldError errors={fieldErrors} field="lot_id" controlId="lot" />
      </div>

      <div>
        <label htmlFor="birthDate">Fecha de nacimiento</label>
        <input
          id="birthDate" {...fieldErrorAttributes(fieldErrors, 'birth_date', 'birthDate')}
          type="date"
          value={birthDate}
          onChange={(event) => setBirthDate(event.target.value)}
        />
        <FieldError errors={fieldErrors} field="birth_date" controlId="birthDate" />
      </div>

      <div>
        <label htmlFor="birthWeight">Peso al nacer (kg)</label>
        <input
          id="birthWeight" {...fieldErrorAttributes(fieldErrors, 'birth_weight', 'birthWeight')}
          type="number"
          min="0"
          step="0.01"
          value={birthWeight}
          onChange={(event) => setBirthWeight(event.target.value)}
        />
        <FieldError errors={fieldErrors} field="birth_weight" controlId="birthWeight" />
      </div>

      <div>
        <label htmlFor="mother">Madre</label>
        <select
          id="mother" {...fieldErrorAttributes(fieldErrors, 'mother_id', 'mother')}
          value={motherId}
          onChange={(event) => setMotherId(event.target.value)}
        >
          <option value="">Sin madre registrada</option>
          {historicalMother && <option value={motherId} disabled>
            Referencia histórica · {motherId}
          </option>}
          {possibleMothers.map((animal) => (
            <option key={animal.id} value={animal.id}>
              {parentLabel(animal)}
            </option>
          ))}
        </select>
        <FieldError errors={fieldErrors} field="mother_id" controlId="mother" />
      </div>

      <div>
        <label htmlFor="father">Padre</label>
        <select
          id="father" {...fieldErrorAttributes(fieldErrors, 'father_id', 'father')}
          value={fatherId}
          onChange={(event) => setFatherId(event.target.value)}
        >
          <option value="">Sin padre registrado</option>
          {historicalFather && <option value={fatherId} disabled>
            Referencia histórica · {fatherId}
          </option>}
          {possibleFathers.map((animal) => (
            <option key={animal.id} value={animal.id}>
              {parentLabel(animal)}
            </option>
          ))}
        </select>
        <FieldError errors={fieldErrors} field="father_id" controlId="father" />
      </div>

      <div>
        <label htmlFor="notes">Notas</label>
        <textarea
          id="notes" {...fieldErrorAttributes(fieldErrors, 'notes', 'notes')}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
        <FieldError errors={fieldErrors} field="notes" controlId="notes" />
      </div>

      {error ? <p role="alert">{error}</p> : null}

      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Guardando...' : animal ? 'Guardar cambios' : 'Guardar animal'}
      </button>
    </form>
  )
}

export default AnimalForm
