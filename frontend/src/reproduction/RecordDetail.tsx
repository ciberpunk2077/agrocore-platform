import type { ReactNode } from 'react'
import ReferenceValue from './ReferenceValue'
import type { ReferenceKind } from './references'
import './RecordDetail.css'
export { animalName } from './reference-labels'

export const dateLabel = (value?: string | null) => value ? value.split('-').reverse().join('/') : 'Sin datos'
export const textLabel = (value?: string | null) => value?.trim() ? value : 'Sin datos'
export const pregnancyStatus = (status: string) => ({ ACTIVE: 'Activa', FINISHED: 'Finalizada', ABORTED: 'Abortada' })[status] ?? 'Sin datos'

export function reference(kind: ReferenceKind, id: string | null, label?: string, animalId?: string, secondary = false) {
  if (!id) return 'Sin datos'
  if (label === id || !label?.trim()) label = undefined
  const fallback = { animal: 'Animal con referencia registrada', event: 'Evento reproductivo con referencia registrada', gender: 'Sexo con referencia registrada', type: 'Tipo con referencia registrada' }[kind]
  return <ReferenceValue key={`${kind}:${id}`} kind={kind} id={id} animalId={animalId} label={label} secondary={secondary}>
    <span className="repro-reference"><span>{label ?? fallback}</span>{secondary && <small className="repro-reference__id">Referencia: {id}</small>}</span>
  </ReferenceValue>
}

export function detailAction(kind: string, id: string, selected: boolean, onOpen: (id: string) => void, onClose: () => void) {
  return <button className="repro-detail-action" id={`repro-open-${kind}-${id}`} type="button" aria-expanded={selected}
    aria-controls={selected ? `repro-panel-${kind}` : undefined} onClick={() => selected ? onClose() : onOpen(id)}>Ver detalles</button>
}

export function recordDetail({ kind, id, title, date, status, loading, error, fields = [], notes, onClose, onRetry, headingRef }: {
  kind: 'breeding' | 'pregnancy' | 'birth' | 'movement'; id: string; title: string; date?: string | null; status?: string
  loading?: string; error?: string; fields?: { label: string; value: ReactNode }[]; notes?: string | null
  onClose: () => void; onRetry: () => void
  headingRef?: (node: HTMLHeadingElement | null) => void
}) {
  const close = () => { onClose(); document.getElementById(`repro-open-${kind}-${id}`)?.focus() }
  const paths = { breeding: 'M8 3a5 5 0 1 0 0 10A5 5 0 0 0 8 3Zm4 9 8 8m-3-8h3v3M17 7l5-5m-5 0h5v5M8 13v9m-4-4h8',
    pregnancy: 'M12 21S3 15 3 9a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 6-9 12-9 12Zm-4-9h8m-4-4v8',
    birth: 'M12 3a9 9 0 1 0 9 9c0-3-1-5-3-6M12 3c-4 1-1 6 2 3M8 11h.01M16 11h.01M8 15c2 3 6 3 8 0',
    movement: 'M4 7h16m-5-5 5 5-5 5M20 17H4m5-5-5 5 5 5' }
  return <section className="repro-detail" id={`repro-panel-${kind}`} aria-labelledby={`repro-title-${kind}`} aria-busy={Boolean(loading)}
    onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); close() } }}>
    <header className="repro-detail__header"><span className="repro-detail__icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={paths[kind]} /></svg></span>
      <div className="repro-detail__heading"><p>Detalle del registro</p><h4 id={`repro-title-${kind}`} tabIndex={-1} ref={headingRef ?? (node => node?.focus())}>{title}</h4>
        <p>{date ? <time dateTime={date}>{dateLabel(date)}</time> : 'Sin datos'}</p></div>
      {status && <span className="repro-detail__badge">Estado: {status}</span>}</header>
    <div className="repro-detail__body">
      {loading ? <p role="status">{loading}</p> : error ? <div><p role="alert">{error}</p><button type="button" onClick={onRetry}>Reintentar detalle</button></div> :
        <dl className="repro-detail__fields" data-fields={fields.length}>{fields.map(field => <div className="repro-detail__field" key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}
          <div className="repro-detail__notes"><dt>Notas</dt><dd>{textLabel(notes)}</dd></div></dl>}
    </div>
    <footer className="repro-detail__footer"><button type="button" onClick={close}><span aria-hidden="true">←</span> Volver al historial</button></footer>
  </section>
}
