import { useEffect, useRef, useState } from 'react'
import type { SubmitEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { getSession } from '../../auth/session'
import FieldError from '../../components/FieldError'
import { fieldErrorAttributes, normalizeApiError } from '../../lib/api-errors'
import { createFarm, getFarmTypes, updateFarm } from '../farms.service'
import type { Farm, FarmCreatePayload, FarmType } from '../types'

function FarmForm({ farm }: { farm?: Farm }) {
  const navigate = useNavigate()
  const [values, setValues] = useState<FarmCreatePayload>(() => ({
    name: farm?.name ?? '', code: farm?.code ?? '', farm_type_id: farm?.farm_type_id ?? '',
    description: farm?.description ?? '', address: farm?.address ?? '', city: farm?.city ?? '',
    state: farm?.state ?? '', country: farm?.country ?? 'México',
  }))
  const [types, setTypes] = useState<FarmType[]>([])
  const [loadingTypes, setLoadingTypes] = useState(true)
  const [typesError, setTypesError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const submitting = useRef(false)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    let active = true
    async function loadTypes() {
      try {
        const session = getSession()
        if (!session) throw new Error('No hay sesión activa.')
        const data = await getFarmTypes(session.access)
        if (active) setTypes(data)
      } catch (cause) {
        if (active) setTypesError(normalizeApiError(cause, 'No fue posible cargar los tipos de finca.').message)
      } finally {
        if (active) setLoadingTypes(false)
      }
    }
    void loadTypes()
    return () => { active = false }
  }, [attempt])

  const validType = types.some((type) => type.id === values.farm_type_id)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current || loadingTypes || typesError || !validType) return
    if (!values.code.trim() || !values.name.trim() || !values.country.trim()) {
      setError('Código, nombre y país son obligatorios.')
      return
    }
    const session = getSession()
    if (!session) { setError('No hay una sesión activa.'); return }
    submitting.current = true
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      // All eight fields are present, including empty optional strings: PUT is complete.
      const payload: FarmCreatePayload = { ...values }
      const saved = farm
        ? await updateFarm(farm.id, payload, session.access)
        : await createFarm(payload, session.access)
      if (mounted.current) navigate(`/farms/${saved.id}`)
    } catch (cause) {
      if (mounted.current) {
        const normalized = normalizeApiError(cause, 'No fue posible guardar la finca. Intenta de nuevo.')
        setError(normalized.message)
        setFieldErrors(normalized.fieldErrors)
      }
    } finally {
      submitting.current = false
      if (mounted.current) setSaving(false)
    }
  }

  const fields: { key: Exclude<keyof FarmCreatePayload, 'farm_type_id'>; label: string; required?: boolean; maxLength?: number }[] = [
    { key: 'code', label: 'Código', required: true, maxLength: 30 },
    { key: 'name', label: 'Nombre', required: true, maxLength: 200 },
    { key: 'description', label: 'Descripción' },
    { key: 'address', label: 'Dirección', maxLength: 255 },
    { key: 'city', label: 'Ciudad', maxLength: 120 },
    { key: 'state', label: 'Estado', maxLength: 120 },
    { key: 'country', label: 'País', required: true, maxLength: 120 },
  ]

  return (
    <form className="farm-form" onSubmit={handleSubmit}>
      {error && <p role="alert">{error}</p>}
      <fieldset disabled={saving}>
        {fields.map(({ key, label, required, maxLength }) => (
          <div className="farm-form__field" key={key}>
            <label htmlFor={`farm-${key}`}>{label}</label>
            {key === 'description' ? (
              <textarea id={`farm-${key}`} value={values[key]} onChange={(event) => setValues({ ...values, [key]: event.target.value })} {...fieldErrorAttributes(fieldErrors, key, `farm-${key}`)} />
            ) : (
              <input id={`farm-${key}`} value={values[key]} required={required} maxLength={maxLength} onChange={(event) => setValues({ ...values, [key]: event.target.value })} {...fieldErrorAttributes(fieldErrors, key, `farm-${key}`)} />
            )}
            <FieldError errors={fieldErrors} field={key} controlId={`farm-${key}`} />
          </div>
        ))}
        <div className="farm-form__field">
          <label htmlFor="farm-type">Tipo de finca</label>
          {loadingTypes && <p role="status">Cargando tipos de finca...</p>}
          {typesError && <div><p role="alert">{typesError}</p><button type="button" onClick={() => { setTypesError(null); setLoadingTypes(true); setAttempt((value) => value + 1) }}>Reintentar tipos</button></div>}
          <select id="farm-type" required disabled={loadingTypes || Boolean(typesError)} value={values.farm_type_id} onChange={(event) => setValues({ ...values, farm_type_id: event.target.value })} {...fieldErrorAttributes(fieldErrors, 'farm_type_id', 'farm-type')}>
            <option value="">Selecciona un tipo de finca</option>
            {farm && !validType && values.farm_type_id === farm.farm_type_id && <option value={farm.farm_type_id} disabled>{farm.farm_type} (No disponible)</option>}
            {types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
          </select>
          {!loadingTypes && !typesError && !types.length && <p>No hay tipos de finca disponibles.</p>}
          {!loadingTypes && !typesError && values.farm_type_id && !validType && <p>Selecciona un tipo disponible antes de guardar.</p>}
          <FieldError errors={fieldErrors} field="farm_type_id" controlId="farm-type" />
        </div>
        <button type="submit" disabled={saving || loadingTypes || Boolean(typesError) || !validType}>{saving ? 'Guardando...' : 'Guardar'}</button>
      </fieldset>
      <Link to={farm ? `/farms/${farm.id}` : '/farms'}>Cancelar</Link>
    </form>
  )
}

export default FarmForm
