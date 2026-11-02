import { apiRequest } from '../lib/api'
import { getDashboardSummary, getUpcomingBirths } from './dashboard.service'
import { isUUID, validDate, isBreeding } from '../breeding/validation'
import { isPregnancy } from '../pregnancy/validation'
import { isBirth } from '../births/validation'
import { isVaccination } from '../vaccinations/validation'
import type { PregnancyRecord } from '../pregnancy/types'
import type { BirthRecord } from '../births/types'
import type { Vaccination } from '../vaccinations/types'
import type { BreedingEvent } from '../breeding/types'
import type { AnimalParentCandidate } from '../animals/types'
import { daysRemaining, remainingLabel } from './presentation'
import { indicatorCount, visibleAnimalName } from './drilldown'
import type { Indicator, DrillRow, DrillSnapshot } from './drilldown'

const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const pregnancy = (r: unknown): r is PregnancyRecord => object(r) && typeof r.animal_id === 'string' && isPregnancy(r, r.animal_id)
const birth = (r: unknown): r is BirthRecord => object(r) && typeof r.mother_id === 'string' && isBirth(r, r.mother_id)
const vaccination = (r: unknown): r is Vaccination => object(r) && typeof r.animal_id === 'string' && isVaccination(r, r.animal_id)
const breeding = (r: unknown): r is BreedingEvent => object(r) && typeof r.animal_id === 'string' && isBreeding(r, r.animal_id)
const candidate = (r: unknown): r is AnimalParentCandidate => object(r) && isUUID(r.id) && typeof r.is_active === 'boolean'
  && typeof r.gender_code === 'string' && ['name', 'internal_id'].every(key => r[key] === null || typeof r[key] === 'string')

async function list<T extends { id: string }>(path: string, guard: (row: unknown) => row is T, accessToken: string, signal: AbortSignal): Promise<T[]> {
  const data = await apiRequest<unknown>(path, { accessToken, signal, expectedStatus: 200, cache: 'no-store' })
  if (!Array.isArray(data) || !data.every(guard) || new Set(data.map(r => r.id)).size !== data.length) throw new Error('El listado recibido no respeta el contrato esperado.')
  return data
}

export async function getDrilldown(kind: Indicator, today: string, token: string, signal: AbortSignal): Promise<DrillSnapshot> {
  if (!validDate(today)) throw new Error('Fecha operativa no disponible.')
  const summaryRead = getDashboardSummary(token, signal)
  if (kind === 'upcoming_births') {
    const [summary, records] = await Promise.all([summaryRead, getUpcomingBirths(token, signal)])
    const rows = records.map((r, index): DrillRow => ({ key: `${r.animal_id}:${index}`, animalId: r.animal_id, animal: visibleAnimalName(r.animal), date: r.expected_birth, status: 'Previsto',
      cells: [{ label: 'Fecha estimada', value: r.expected_birth }, { label: 'Días restantes', value: remainingLabel(daysRemaining(r.expected_birth, today)) }] }))
    const datesAgree = records.every(r => { const days = daysRemaining(r.expected_birth, today); return days !== null && days >= 0 && days <= 30 })
    return { expected: summary.upcoming_births, rows: datesAgree && rows.length === summary.upcoming_births ? rows : [],
      limitation: !datesAgree ? 'La agenda no coincide con la ventana de la fecha operativa. Actualiza el contexto y vuelve a consultar.' : rows.length !== summary.upcoming_births ? 'El contador y la agenda cambiaron entre consultas. Actualiza para obtener una lectura coherente.' : null }
  }
  const recordsRead = kind === 'pregnancies' ? list('/pregnancies/', pregnancy, token, signal)
    : kind === 'births_this_month' ? list('/births/', birth, token, signal) : list('/vaccinations/', vaccination, token, signal)
  const relatedRead = kind === 'pregnancies' ? list('/breeding/', breeding, token, signal)
    : kind === 'births_this_month' ? list('/pregnancies/', pregnancy, token, signal) : Promise.resolve([])
  const [summary, records, animals, related] = await Promise.all([summaryRead, recordsRead,
    list('/animals/parents/candidates', candidate, token, signal), relatedRead])
  const names = new Map(animals.map(a => [a.id, [a.name, a.internal_id].map(visibleAnimalName)
    .filter(part => part !== 'Identificación no disponible').join(' · ') || 'Identificación no disponible']))
  const relatedIds = new Set(related.map(r => r.id))
  const rows: DrillRow[] = []
  let unresolved = false
  for (const record of records) {
    if (kind === 'pregnancies') {
      const r = record as PregnancyRecord
      if (!r.confirmed || r.status !== 'ACTIVE') continue
      if (!names.has(r.animal_id) || !relatedIds.has(r.breeding_id)) { unresolved = true; continue }
      rows.push({ key: r.id, animalId: r.animal_id, animal: names.get(r.animal_id)!, date: r.diagnosis_date, status: 'Activa', cells: [{ label: 'Diagnóstico', value: r.diagnosis_date }, { label: 'Estado', value: 'Activa · confirmada' }, { label: 'Fecha estimada de parto', value: r.expected_birth }] })
    } else if (kind === 'births_this_month') {
      const r = record as BirthRecord
      if (r.birth_date.slice(0, 7) !== today.slice(0, 7)) continue
      if (!names.has(r.mother_id) || !relatedIds.has(r.pregnancy_id) || (r.calf_id !== null && !names.has(r.calf_id))) { unresolved = true; continue }
      rows.push({ key: r.id, animalId: r.mother_id, animal: names.get(r.mother_id)!, date: r.birth_date, status: r.alive ? 'Vivo' : 'No vivo', cells: [{ label: 'Fecha del parto', value: r.birth_date }, { label: 'Cría', value: r.calf_id ? names.get(r.calf_id)! : 'Sin cría vinculada' }, { label: 'Estado de la cría al parto', value: r.alive ? 'Vivo' : 'No vivo' }] })
    } else {
      const r = record as Vaccination
      if (!r.is_active || r.next_application_date === null || r.next_application_date > today) continue
      if (!names.has(r.animal_id)) { unresolved = true; continue }
      rows.push({ key: r.id, animalId: r.animal_id, animal: names.get(r.animal_id)!, date: r.next_application_date, status: r.next_application_date < today ? 'Vencida' : 'Vence hoy', cells: [{ label: 'Vacuna', value: r.vaccine_name.trim() || 'Sin datos' }, { label: 'Fecha programada', value: r.next_application_date }, { label: 'Situación por fecha', value: r.next_application_date < today ? 'Vencida' : 'Vence hoy' }] })
    }
  }
  const expected = indicatorCount(summary, kind)
  const limitation = unresolved ? 'No se puede verificar la pertenencia de todas las relaciones con los contratos disponibles. Los catálogos de consulta excluyen animales eliminados o relaciones archivadas que el KPI sí puede contar. No se presenta un listado parcial como equivalente.'
    : rows.length !== expected ? 'El listado verificable y el contador no coinciden. Puede haber cambios entre consultas o relaciones históricas no disponibles. Actualiza; no se presenta un conteo distinto como equivalente.' : null
  return { expected, rows: limitation ? [] : rows, limitation }
}
