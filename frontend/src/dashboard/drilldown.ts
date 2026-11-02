import type { DashboardSummary } from './types'
export const indicators = {
  pregnancies: { title: 'Gestaciones', definition: 'Registros de gestación activos, confirmados y con estado ACTIVE; animal y evento reproductivo de la organización.' },
  births_this_month: { title: 'Nacimientos este mes', definition: 'Registros de parto activos del mes y año de la fecha operativa; madre, gestación y cría vinculada de la organización. Cuenta partos, incluidos los no vivos, no crías ni madres únicas.' },
  upcoming_births: { title: 'Próximos nacimientos', definition: 'Gestaciones activas y confirmadas, con estado ACTIVE y fecha estimada entre hoy y hoy +30 días, inclusive; animal y evento reproductivo de la organización.' },
  vaccinations_due: { title: 'Vacunaciones pendientes', definition: 'Registros de vacunación activos con próxima aplicación no nula y menor o igual a la fecha operativa; animal de la organización. Cuenta registros, no animales únicos ni aplicaciones futuras.' },
} as const
export type Indicator = keyof typeof indicators
export const isIndicator = (value?: string): value is Indicator => !!value && Object.hasOwn(indicators, value)
export interface DrillRow { key: string; animalId: string; animal: string; date: string; status: string; cells: { label: string; value: string }[] }
export interface DrillSnapshot { expected: number; rows: DrillRow[]; limitation: string | null }
export const indicatorCount = (summary: DashboardSummary, kind: Indicator) => summary[kind]
export const visibleAnimalName = (value: string | null | undefined) => value?.trim() && !/^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i.test(value.trim()) ? value.trim() : 'Identificación no disponible'
