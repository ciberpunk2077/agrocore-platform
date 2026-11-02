import { Badge } from '../../ui/components'
import { displayValue, identification } from '../inventory'
import type { Animal } from '../types'

export function AnimalIdentity({ animal }: { animal: Animal }) {
  // The response has species names, but no codes for choosing species-specific icons.
  return <span className="inventory-identity"><span className="inventory-identity__icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="m5 9-2-5 5 2h8l5-2-2 5v9l-4 3H9l-4-3ZM8 12h.01M16 12h.01M9 17h6" /></svg></span>
    <span><strong>{identification(animal)}</strong><small>ID interno: {displayValue(animal.internal_id)}</small>
      <small>Arete oficial: {displayValue(animal.official_tag)}</small><small>Arete electrónico: {displayValue(animal.electronic_tag)}</small></span></span>
}
export function AnimalStatusBadge({ animal }: { animal: Animal }) {
  // Preserve catalog meaning without guessing status-to-color mappings.
  return <Badge tone="neutral">{displayValue(animal.status)}</Badge>
}
