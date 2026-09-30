import { useState } from 'react'

import VaccinationForm from './VaccinationForm'
import VaccinationHistory from './VaccinationHistory'

interface VaccinationsProps {
  animalId: string
}

function Vaccinations({ animalId }: VaccinationsProps) {
  const [historyVersion, setHistoryVersion] = useState(0)

  return (
    <section className="vaccinations" aria-label="Vacunaciones">
      <h2>Vacunaciones</h2>
      <VaccinationForm animalId={animalId} onSaved={() => setHistoryVersion((version) => version + 1)} />
      <VaccinationHistory animalId={animalId} version={historyVersion} />
    </section>
  )
}

export default Vaccinations
