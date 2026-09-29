import { useNavigate } from 'react-router-dom'

import { clearSession } from '../auth/session'

function DashboardPage() {
  const navigate = useNavigate()

  function handleLogout() {
    clearSession()
    navigate('/login', { replace: true })
  }

  return (
    <main>
      <h1>AgroCore</h1>
      <p>Dashboard</p>

      <button type="button" onClick={handleLogout}>
        Cerrar sesión
      </button>
    </main>
  )
}

export default DashboardPage