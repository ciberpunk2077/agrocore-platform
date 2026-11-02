import type { BusinessTime, CurrentContext } from './types'

const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const uuid = (v: unknown) => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v)
export function validCivilDate(v: unknown): v is string {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v) || v.startsWith('0000')) return false
  const date = new Date(`${v}T00:00:00Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === v
}

export function isBusinessTime(v: unknown): v is BusinessTime {
  if (!object(v) || !validCivilDate(v.business_today) || typeof v.effective_timezone !== 'string'
    || !v.effective_timezone || v.effective_timezone.trim() !== v.effective_timezone || v.effective_timezone.length > 64) return false
  const timestamp = (t: unknown): t is string => typeof t === 'string'
    && /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(t)
    && validCivilDate(t.slice(0, 10)) && Number.isFinite(Date.parse(t))
  if (!timestamp(v.server_now) || !timestamp(v.valid_until)) return false
  const duration = Date.parse(v.valid_until) - Date.parse(v.server_now)
  if (duration <= 0 || duration > 60000) return false
  try {
    const formatter = new Intl.DateTimeFormat('en-US', { timeZone: v.effective_timezone, year: 'numeric', month: '2-digit', day: '2-digit' })
    const day = (instant: number) => {
      const parts = formatter.formatToParts(new Date(instant))
      const part = (name: string) => parts.find(p => p.type === name)?.value
      return `${part('year')}-${part('month')}-${part('day')}`
    }
    return day(Date.parse(v.server_now)) === v.business_today && day(Date.parse(v.valid_until) - 1) === v.business_today
  } catch { return false }
}

export function parseCurrentContext(v: unknown): CurrentContext {
  if (!object(v) || typeof v.user !== 'string' || !object(v.current_user) || !uuid(v.current_user.id)
    || !['email', 'first_name', 'last_name'].every(k => typeof (v.current_user as Record<string, unknown>)[k] === 'string')
    || !(v.organization === null || (object(v.organization) && uuid(v.organization.id)
      && typeof v.organization.name === 'string' && typeof v.organization.code === 'string'))
    || !(v.membership === null || (object(v.membership) && uuid(v.membership.id) && typeof v.membership.is_default === 'boolean'))
    || !(v.role === null || ['OWNER', 'ADMIN', 'VETERINARIAN', 'OPERATOR', 'VIEWER'].includes(v.role as string))
    || typeof v.can_read !== 'boolean' || typeof v.can_write !== 'boolean') throw new Error('Respuesta de contexto inválida.')
  // A missing/invalid temporal extension must not hide existing READ data.
  return { ...v, business_time: v.organization !== null && isBusinessTime(v.business_time) ? v.business_time : null } as unknown as CurrentContext
}
