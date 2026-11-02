import { useEffect, useState } from 'react'
import { getAnimalTimeline, type TimelineEvent } from '../animal-detail.service'

const eventIcons: Record<string, string> = {
  weight: 'M4 7h16l2 14H2zM9 7V5a3 3 0 0 1 6 0v2M12 12v4',
  movement: 'M3 7h17l-4-4m4 4-4 4M21 17H4l4-4m-4 4 4 4',
  vaccination: 'm16 3 5 5M14 5l5 5M3 21l4-4M6 13l7-7 5 5-7 7z',
  breeding: 'M12 21S2 14 2 8a5 5 0 0 1 10-1 5 5 0 0 1 10 1c0 6-10 13-10 13Z',
  pregnancy: 'M12 3v6M9 6h6M5 12a7 7 0 1 0 14 0',
  birth: 'M5 12a7 7 0 1 0 14 0M8 14h.01M16 14h.01M9 18h6M12 3v5',
}

export default function AnimalTimeline({ animalId, accessToken, current }: { animalId: string; accessToken: string; current: () => boolean }) {
  const [state, setState] = useState<{ status: 'loading' | 'error' | 'loaded'; events: TimelineEvent[] }>({ status: 'loading', events: [] })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getAnimalTimeline(animalId, accessToken, controller.signal).then(events => {
      if (!controller.signal.aborted && current()) setState({ status: 'loaded', events })
    }).catch(() => {
      if (!controller.signal.aborted && current()) setState({ status: 'error', events: [] })
    })
    return () => controller.abort()
  }, [animalId, accessToken, current, attempt])
  if (state.status === 'loading') return <p role="status">Cargando historial...</p>
  if (state.status === 'error') return <div><p role="alert">No fue posible consultar el historial. No se muestran datos sustitutos.</p><button type="button" onClick={() => { setState({ status: 'loading', events: [] }); setAttempt(v => v + 1) }}>Reintentar</button></div>
  if (!state.events.length) return <p className="expedient-empty">Sin datos: no hay eventos registrados para este animal.</p>
  return <ol className="animal-timeline">{[...state.events].sort((a, b) => b.date.localeCompare(a.date)).map(event => <li key={`${event.event_type}:${event.id}`}>
    <span className="animal-timeline__marker"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={eventIcons[event.event_type] ?? 'M4 5h16v16H4zM8 3v4M16 3v4M4 10h16'} /></svg></span>
    <time dateTime={event.date}>{event.date}</time><div><h3>{event.title || 'Sin datos'}</h3><p>{event.description || 'Sin datos'}</p></div>
  </li>)}</ol>
}
