import { Link } from 'react-router-dom'

import AnimalForm from '../animals/components/form/AnimalForm'

function NewAnimalPage() {
  return (
    <section>
      <Link to="/animals">← Volver a animales</Link>

      <h1>Nuevo animal</h1>
      <p>Registra un nuevo animal en AgroCore.</p>

      <AnimalForm />
    </section>
  )
}

export default NewAnimalPage