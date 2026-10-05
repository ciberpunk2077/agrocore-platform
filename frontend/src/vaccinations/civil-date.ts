const formatter = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Mexico_City', calendar: 'gregory', numberingSystem: 'latn',
  year: 'numeric', month: '2-digit', day: '2-digit',
})

export function vaccinationToday(instant: Date = new Date()): string {
  const parts = formatter.formatToParts(instant)
  const part = (type: 'year' | 'month' | 'day') => parts.find((item) => item.type === type)!.value
  return `${part('year').padStart(4, '0')}-${part('month')}-${part('day')}`
}
