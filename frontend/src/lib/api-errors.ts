import { ApiError } from './api'

export interface NormalizedApiError {
  message: string
  fieldErrors: Record<string, string[]>
}

function fieldLocation(location: unknown): string | null {
  if (!Array.isArray(location) || !location.every((part) =>
    (typeof part === 'string' && part.length > 0) ||
    (typeof part === 'number' && Number.isInteger(part) && part >= 0))) return null

  const parts = [...location]
  const source = parts[0]
  if (source === 'body' || source === 'query' || source === 'path') parts.shift()
  // All consumed body endpoints declare their Ninja schema parameter as `payload`.
  if (source === 'body' && parts[0] === 'payload') parts.shift()
  return parts.length ? parts.join('.') : null
}

export function normalizeApiError(
  cause: unknown,
  fallback = 'No fue posible completar la operación. Intenta de nuevo.',
): NormalizedApiError {
  const message = fallback.trim() || 'No fue posible completar la operación. Intenta de nuevo.'
  const fieldErrors: Record<string, string[]> = Object.create(null)
  if (!(cause instanceof ApiError) || ![400, 422, 403, 404].includes(cause.status)) {
    return { message, fieldErrors }
  }

  const detail = cause.data && typeof cause.data === 'object' && 'detail' in cause.data
    ? cause.data.detail : null
  if (typeof detail === 'string' && detail.trim()) {
    return { message: detail.trim(), fieldErrors }
  }

  if (cause.status === 422 && Array.isArray(detail)) {
    const messages: string[] = []
    for (const item of detail) {
      if (!item || typeof item !== 'object' || typeof item.msg !== 'string' || !item.msg.trim()) continue
      const text = item.msg.trim()
      const field = fieldLocation(item.loc)
      if (field) {
        (fieldErrors[field] ??= []).push(text)
        messages.push(`${field}: ${text}`)
      } else {
        messages.push(text)
      }
    }
    if (messages.length) return { message: messages.join('; '), fieldErrors }
  }

  return {
    message: cause.status === 403 ? 'No tienes permiso para realizar esta operación.' : message,
    fieldErrors,
  }
}

export function fieldErrorAttributes(
  errors: Record<string, string[]>, field: string, controlId: string,
) {
  const invalid = Object.hasOwn(errors, field) && errors[field].length > 0
  return {
    'aria-invalid': invalid || undefined,
    'aria-describedby': invalid ? `${controlId}-api-error` : undefined,
  }
}
