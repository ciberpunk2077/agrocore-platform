import { useCallback, useEffect, useState } from 'react'
import { getSession, getSessionRevision } from '../../auth/session'
import { ApiError } from '../../lib/api'
import { normalizeApiError } from '../../lib/api-errors'
import { getVaccination } from '../vaccinations.service'
import type { Vaccination } from '../types'
import VaccinationEditForm from './VaccinationEditForm'
import WriteOnly from '../../auth/WriteOnly'
import './VaccinationDetail.css'

type Props = {
  vaccinationId: string; animalId: string; birthDate: string | null
  onCancel: () => void; onSaved: () => void; onRecheck: () => void
  readOnly?: boolean
}

export default function VaccinationPreparation(props: Props) {
  const [attempt, setAttempt] = useState(0)
  return <LoadedVaccination key={attempt} {...props} onRetry={() => setAttempt((value) => value + 1)} />
}

function LoadedVaccination({ vaccinationId, animalId, birthDate, onCancel, onSaved, onRecheck, onRetry, readOnly }: Props & { onRetry: () => void }) {
  const [state, setState] = useState<{ status: 'loading' } | { status: 'error'; message: string; retry: boolean } | { status: 'ready'; record: Vaccination }>({ status: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    const revision = getSessionRevision()
    const current = () => !controller.signal.aborted && revision === getSessionRevision()
    async function load() {
      const session = getSession()
      if (!session) { setState({ status: 'error', message: 'No hay una sesión activa.', retry: false }); return }
      try {
        const record = await getVaccination(vaccinationId, animalId, session.access, controller.signal)
        if (current()) setState({ status: 'ready', record })
      } catch (cause) {
        if (!current()) return
        const status = cause instanceof ApiError ? cause.status : null
        setState({ status: 'error', retry: cause instanceof ApiError ? cause.status >= 500 : cause instanceof TypeError,
          message: status === 404 ? 'La vacunación ya no está disponible o no fue encontrada.'
            : status === 401 ? 'La sesión ya no está disponible. Inicia sesión de nuevo.'
            : normalizeApiError(cause, 'No fue posible obtener un detalle válido para esta vacunación y animal.').message })
      }
    }
    void load()
    return () => controller.abort()
  }, [vaccinationId, animalId])
  if (state.status === 'loading') return <section><p role="status">Cargando vacunación completa...</p><button type="button" onClick={onCancel}>Cancelar</button></section>
  if (state.status === 'error') return <section><p role="alert">{state.message}</p>
    {state.retry && <button type="button" onClick={onRetry}>Reintentar consulta del detalle</button>}
    <button type="button" onClick={onCancel}>Volver</button></section>
  if (readOnly) return <VaccinationDetail record={state.record} onClose={onCancel} />
  return <WriteOnly><VaccinationEditForm record={state.record} vaccinationId={vaccinationId} animalId={animalId} birthDate={birthDate}
    onCancel={onCancel} onSaved={onSaved} onRecheck={onRecheck} /></WriteOnly>
}

const detailIcons = {
  syringe: 'm18 2 4 4m-5-3 4 4M4 14l6 6 10-10-6-6zM2 22l5-5m1-7 3 3m0-6 3 3',
  calendar: 'M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2ZM7 14h3m4 0h3m-10 4h3',
  dose: 'M9 3h6m-3 0v6m-4 0h8v12H8zM8 14h4m-4 3h3',
  batch: 'M3 3h9l9 9-9 9-9-9zM7 7h.01',
  veterinarian: 'M8 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM2 22v-5a6 6 0 0 1 12 0v5m4-9v8m-4-4h8',
  notes: 'M5 2h10l4 4v16H5zM14 2v5h5M9 11h6m-6 4h6m-6 4h4',
  back: 'm10 5-7 7 7 7M3 12h18',
} as const

function DetailIcon({ name }: { name: keyof typeof detailIcons }) {
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={detailIcons[name]} /></svg>
}

const display = (value?: string | null) => value?.trim() ? value : 'Sin datos'
const dateLabel = (value?: string | null) => value ? value.split('-').reverse().join('/') : 'Sin datos'

export function VaccinationDetail({ record, onClose }: { record: Vaccination; onClose: () => void }) {
  const focusHeading = useCallback((node: HTMLHeadingElement | null) => node?.focus(), [])
  const titleId = `vaccination-detail-title-${record.id}`
  const fields = [
    { label: 'Fecha de aplicación', value: dateLabel(record.application_date), date: record.application_date, icon: 'calendar' },
    { label: 'Próxima aplicación', value: dateLabel(record.next_application_date), date: record.next_application_date, icon: 'calendar' },
    { label: 'Dosis', value: display(record.dose), icon: 'dose' },
    { label: 'Lote', value: display(record.batch), icon: 'batch' },
  ] as const
  return <section className="vaccination-detail" aria-labelledby={titleId}>
    <header className="vaccination-detail__header">
      <span className="vaccination-detail__icon vaccination-detail__icon--hero"><DetailIcon name="syringe" /></span>
      <div className="vaccination-detail__heading">
        <p className="vaccination-detail__eyebrow">Detalle de vacunación</p>
        <h3 id={titleId} tabIndex={-1} ref={focusHeading}>{display(record.vaccine_name)}</h3>
        <p>Fecha de aplicación: {record.application_date ? <time dateTime={record.application_date}>{dateLabel(record.application_date)}</time> : 'Sin datos'}</p>
      </div>
      <span className={`vaccination-detail__status${record.is_active === false ? ' vaccination-detail__status--inactive' : ''}`}>
        <span className="vaccination-detail__status-dot" aria-hidden="true" />
        Estado del registro: {record.is_active === true ? 'Activa' : record.is_active === false ? 'Inactiva' : 'Sin datos'}
      </span>
    </header>
    <div className="vaccination-detail__body">
      <div className="vaccination-detail__group">
      <h4 className="vaccination-detail__group-title">Información de la aplicación</h4>
      <dl className="vaccination-detail__facts">
        {fields.map(field => <div className="vaccination-detail__fact" key={field.label}>
          <dt><span className="vaccination-detail__icon"><DetailIcon name={field.icon} /></span>{field.label}</dt>
          <dd>{'date' in field && field.date ? <time dateTime={field.date}>{field.value}</time> : field.value}</dd>
        </div>)}
      </dl>
      </div>
      <div className="vaccination-detail__group">
      <h4 className="vaccination-detail__group-title">Profesional y observaciones</h4>
      <dl className="vaccination-detail__additional">
        <div className="vaccination-detail__block"><dt><DetailIcon name="veterinarian" />Veterinario</dt><dd>{display(record.veterinarian)}</dd></div>
        <div className="vaccination-detail__block vaccination-detail__block--notes"><dt><DetailIcon name="notes" />Notas</dt><dd>{display(record.notes)}</dd></div>
      </dl>
      </div>
    </div>
    <footer className="vaccination-detail__footer"><button type="button" onClick={onClose}><DetailIcon name="back" />Volver al historial</button></footer>
  </section>
}
