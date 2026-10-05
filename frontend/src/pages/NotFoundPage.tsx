import { Link } from 'react-router-dom'

import { useSession } from '../auth/useSession'

function NotFoundPage() {
  const { session } = useSession()

  return (
    <main aria-labelledby="not-found-title">
      <h1 id="not-found-title">404 — Página no encontrada</h1>
      <p>La página que buscas no existe. Revisa la dirección o vuelve a la aplicación.</p>
      <Link to={session ? '/dashboard' : '/login'}>
        {session ? 'Volver al Dashboard' : 'Ir a iniciar sesión'}
      </Link>
    </main>
  )
}

export default NotFoundPage
