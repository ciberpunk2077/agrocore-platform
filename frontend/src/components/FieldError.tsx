function FieldError({ errors, field, controlId }: {
  errors: Record<string, string[]>
  field: string
  controlId: string
}) {
  if (!Object.hasOwn(errors, field) || !errors[field].length) return null
  return <p id={`${controlId}-api-error`} role="alert">{errors[field].join('; ')}</p>
}

export default FieldError
