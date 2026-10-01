import './BirthHistory.css'
import type { Animal, Gender } from '../../animals/types'
import type { BirthRecord } from '../types'

interface BirthHistoryProps {
  history: BirthRecord[]
  animals: Animal[]
  genders: Gender[]
  disabled: boolean
}

function formatDate(value: string): string {
  return value.split('-').reverse().join('/')
}

function animalLabel(animal: Animal): string {
  return (
    [animal.name?.trim(), animal.internal_id?.trim()]
      .filter(Boolean)
      .join(' · ') ||
    'Animal sin identificación'
  )
}

function BirthHistory({
  history,
  animals,
  genders,
}: BirthHistoryProps) {
  const animalNames = new Map(
    animals.map((animal) => [
      animal.id,
      animalLabel(animal),
    ]),
  )

  const genderNames = new Map(
    genders.map((gender) => [
      gender.id,
      gender.name,
    ]),
  )

  if (history.length === 0) {
    return (
      <section className="birth-history">
        <h3>Historial de partos</h3>

        <p>
          Este animal todavía no tiene partos
          registrados.
        </p>
      </section>
    )
  }

  return (
    <section className="birth-history">
      <h3>Historial de partos</h3>

      <div className="birth-history__list">
        {history.map((birth) => (
          <article
            className="birth-history__item"
            key={birth.id}
          >
            <div className="birth-history__field">
              <strong>Fecha del parto</strong>
              <span>
                {formatDate(birth.birth_date)}
              </span>
            </div>

            <div className="birth-history__field">
              <strong>Cría</strong>
              <span>
                {birth.calf_id
                  ? animalNames.get(
                      birth.calf_id,
                    ) ?? 'Cría no disponible'
                  : 'No registrada'}
              </span>
            </div>

            <div className="birth-history__field">
              <strong>Sexo</strong>
              <span>
                {birth.calf_gender_id
                  ? genderNames.get(
                      birth.calf_gender_id,
                    ) ?? 'Sexo no disponible'
                  : 'No indicado'}
              </span>
            </div>

            <div className="birth-history__field">
              <strong>Peso</strong>
              <span>
                {birth.birth_weight} kg
              </span>
            </div>

            <div className="birth-history__field">
              <strong>Estado</strong>
              <span>
                {birth.alive
                  ? 'Viva'
                  : 'Muerta'}
              </span>
            </div>

            <div className="birth-history__field">
              <strong>Distocia</strong>
              <span>
                {birth.dystocia
                  ? 'Sí'
                  : 'No'}
              </span>
            </div>

            {birth.notes?.trim() && (
              <div className="birth-history__field birth-history__notes">
                <strong>Notas</strong>
                <span>
                  {birth.notes.trim()}
                </span>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  )
}

export default BirthHistory