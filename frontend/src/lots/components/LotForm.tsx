import { useEffect, useRef, useState } from 'react'
import type { SubmitEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getSession } from '../../auth/session'
import FieldError from '../../components/FieldError'
import type { Farm } from '../../farms/types'
import { fieldErrorAttributes, normalizeApiError } from '../../lib/api-errors'
import { createLot, updateLot } from '../lots.service'
import type { Lot, LotCreatePayload } from '../types'

function LotForm({ lot, initialFarmId, farms }: { lot?: Lot; initialFarmId: string; farms: Farm[] }) {
  const navigate = useNavigate()
  const [farmId, setFarmId] = useState(lot?.farm_id ?? initialFarmId)
  const [code, setCode] = useState(lot?.code ?? '')
  const [name, setName] = useState(lot?.name ?? '')
  const [description, setDescription] = useState(lot?.description ?? '')
  const [capacity, setCapacity] = useState(String(lot?.capacity ?? 0))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const submitting = useRef(false)
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const selectedFarm = farms.find((farm) => farm.id === farmId)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current) return
    const numericCapacity = Number(capacity)
    if (!selectedFarm || !code.trim() || !name.trim() || !capacity.trim() || !Number.isInteger(numericCapacity) || numericCapacity < 0) {
      setError('Selecciona una finca disponible, completa código y nombre, e indica una capacidad entera mayor o igual a 0.')
      return
    }
    const session = getSession()
    if (!session) { setError('No hay una sesión activa.'); return }
    submitting.current = true
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const payload: LotCreatePayload = { farm_id: farmId, code, name, description, capacity: numericCapacity }
      const saved = lot ? await updateLot(lot.id, payload, session.access) : await createLot(payload, session.access)
      if (mounted.current) navigate(`/lots/${saved.id}`)
    } catch (cause) {
      if (mounted.current) {
        const normalized = normalizeApiError(cause, 'No fue posible guardar el lote. Intenta de nuevo.')
        setError(normalized.message)
        setFieldErrors(normalized.fieldErrors)
      }
    } finally {
      submitting.current = false
      if (mounted.current) setSaving(false)
    }
  }

  return <form className="lot-form" onSubmit={handleSubmit}>
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={saving}>
      <div className="lot-form__field">
        <label htmlFor="lot-farm">Finca</label>
        <select id="lot-farm" value={farmId} required onChange={(event) => setFarmId(event.target.value)} {...fieldErrorAttributes(fieldErrors, 'farm_id', 'lot-farm')}>
          <option value="">Selecciona una finca</option>
          {lot && !selectedFarm && farmId === lot.farm_id && <option value={lot.farm_id} disabled>Finca no disponible · {lot.farm_id}</option>}
          {farms.map((farm) => <option key={farm.id} value={farm.id}>{farm.code} · {farm.name}</option>)}
        </select>
        {selectedFarm ? <p>{lot ? 'Finca seleccionada' : 'El lote se creará en'}: {selectedFarm.code} · {selectedFarm.name}</p> : <p>Selecciona una finca disponible antes de guardar.</p>}
        <FieldError errors={fieldErrors} field="farm_id" controlId="lot-farm" />
      </div>
      <div className="lot-form__field"><label htmlFor="lot-code">Código</label><input id="lot-code" value={code} required maxLength={30} onChange={(event) => setCode(event.target.value)} {...fieldErrorAttributes(fieldErrors, 'code', 'lot-code')} /><FieldError errors={fieldErrors} field="code" controlId="lot-code" /></div>
      <div className="lot-form__field"><label htmlFor="lot-name">Nombre</label><input id="lot-name" value={name} required maxLength={200} onChange={(event) => setName(event.target.value)} {...fieldErrorAttributes(fieldErrors, 'name', 'lot-name')} /><FieldError errors={fieldErrors} field="name" controlId="lot-name" /></div>
      <div className="lot-form__field"><label htmlFor="lot-description">Descripción</label><textarea id="lot-description" value={description} onChange={(event) => setDescription(event.target.value)} {...fieldErrorAttributes(fieldErrors, 'description', 'lot-description')} /><FieldError errors={fieldErrors} field="description" controlId="lot-description" /></div>
      <div className="lot-form__field"><label htmlFor="lot-capacity">Capacidad</label><input id="lot-capacity" type="number" min="0" step="1" required value={capacity} onChange={(event) => setCapacity(event.target.value)} {...fieldErrorAttributes(fieldErrors, 'capacity', 'lot-capacity')} /><FieldError errors={fieldErrors} field="capacity" controlId="lot-capacity" /></div>
      <button type="submit" disabled={saving || !selectedFarm}>{saving ? 'Guardando...' : 'Guardar'}</button>
    </fieldset>
    <Link to={lot ? `/lots/${lot.id}` : `/farms/${initialFarmId}`}>Cancelar</Link>
  </form>
}

export default LotForm
