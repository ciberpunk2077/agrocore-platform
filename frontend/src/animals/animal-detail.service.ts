import { apiRequest } from '../lib/api'
import { isUUID, validDate } from '../breeding/validation'
import { getAnimalWeightHistory, getWeight } from '../weights/weights.service'

export interface TimelineEvent { id: string; date: string; event_type: string; title: string; description: string }

export async function getAnimalTimeline(animalId: string, accessToken: string, signal?: AbortSignal): Promise<TimelineEvent[]> {
  if (!isUUID(animalId)) throw new Error('Animal inválido.')
  const data = await apiRequest<unknown>(`/timeline/animal/${animalId}`, { accessToken, signal, cache: 'no-store', expectedStatus: 200 })
  if (!Array.isArray(data) || !data.every(item => item && isUUID(item.id) && validDate(item.date)
    && typeof item.event_type === 'string' && typeof item.title === 'string' && typeof item.description === 'string')
    || new Set(data.map(item => `${item.event_type}:${item.id}`)).size !== data.length) throw new Error('Respuesta de historial inválida.')
  return data as TimelineEvent[]
}

export async function getLatestAnimalWeight(animalId: string, token: string, signal?: AbortSignal): Promise<string | null> {
  if (!isUUID(animalId)) throw new Error('Animal inválido.')
  const rows = await getAnimalWeightHistory(animalId, token, signal)
  if (!Array.isArray(rows) || !rows.every(row => row && isUUID(row.id) && validDate(row.date)
    && typeof row.weight === 'string' && /^\d+(?:\.\d+)?$/.test(row.weight))
    || new Set(rows.map(row => row.id)).size !== rows.length) throw new Error('Pesajes inválidos.')
  if (!rows.length) return null
  const ordered = [...rows].sort((a, b) => b.date.localeCompare(a.date))
  // History has no creation timestamp: do not invent an order for same-day records.
  if (ordered.length > 1 && ordered[0].date === ordered[1].date) throw new Error('Varios pesajes en la fecha más reciente; consultar el historial.')
  const latest = ordered[0]
  const detail = await getWeight(latest.id, token, signal)
  if (detail.animal_id !== animalId || detail.id !== latest.id || detail.date !== latest.date || detail.weight !== latest.weight) throw new Error('El pesaje no corresponde al animal.')
  return `${latest.weight} kg · ${latest.date}`
}
