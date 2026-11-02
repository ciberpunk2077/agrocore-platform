import { validDate } from '../breeding/validation'
import type { AnimalParentReference } from './types'

export function animalParentLabel(id: string | null, parent?: AnimalParentReference | null): string {
  if (!id) return 'Sin datos'
  if (!parent) return `Referencia · ${id}`
  const label = [parent.internal_id?.trim(), parent.name?.trim()].filter(Boolean).join(' · ') || id
  return `${label}${parent.is_deleted ? ' (Referencia histórica)' : parent.is_active ? '' : ' (Inactivo)'}`
}

export const animalSections = [
  { slug: '', label: 'Información general', description: 'Identificación y datos del animal', icon: 'active' },
  { slug: 'salud', label: 'Salud y vacunaciones', description: 'Vacunas e historial sanitario', icon: 'vaccination' },
  { slug: 'pesajes', label: 'Pesajes', description: 'Peso y evolución del animal', icon: 'weight' },
  { slug: 'reproduccion', label: 'Reproducción', description: 'Eventos, gestaciones y partos', icon: 'pregnancy' },
  { slug: 'movimientos', label: 'Movimientos', description: 'Traslados y ubicación', icon: 'refresh' },
  { slug: 'produccion', label: 'Producción', description: 'Registros productivos', icon: 'herd' },
  { slug: 'historial', label: 'Historial / Timeline', description: 'Cronología de eventos', icon: 'calendar' },
] as const

export function animalSectionPath(animalId: string, section?: string) {
  return `/animals/${encodeURIComponent(animalId)}${section ? `/${section}` : ''}`
}

export function animalAge(birthDate: string | null, businessToday: string | null): string {
  if (!validDate(birthDate) || !validDate(businessToday) || birthDate > businessToday) return 'Sin datos'
  const birth = new Date(`${birthDate}T00:00:00Z`), today = new Date(`${businessToday}T00:00:00Z`)
  let months = (today.getUTCFullYear() - birth.getUTCFullYear()) * 12 + today.getUTCMonth() - birth.getUTCMonth()
  if (today.getUTCDate() < birth.getUTCDate()) months--
  if (months < 1) {
    const days = Math.floor((today.getTime() - birth.getTime()) / 86400000)
    return `${days} ${days === 1 ? 'día' : 'días'}`
  }
  const years = Math.floor(months / 12), remaining = months % 12
  return [years ? `${years} ${years === 1 ? 'año' : 'años'}` : '', remaining ? `${remaining} ${remaining === 1 ? 'mes' : 'meses'}` : ''].filter(Boolean).join(' y ')
}
