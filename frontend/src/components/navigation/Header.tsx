import { useNavigate } from 'react-router-dom'

import { clearSession } from '../../auth/session'
import { useCurrentContext } from '../../auth/current-context'
import './Header.css'

function Header() {
  const navigate = useNavigate()
  const { currentUser: user, currentOrganization, currentRole } = useCurrentContext()

  const fullName = user
    ? `${user.first_name} ${user.last_name}`.trim()
    : ''

  function handleLogout() {
    clearSession()
    navigate('/login', { replace: true })
  }

  return (
    <header className="app-header">
      <div className="app-header__brand">AgroCore</div>

      <div className="app-header__actions">
        {user && (
          <div className="app-header__user">
            {fullName && (
              <span className="app-header__user-name">{fullName}</span>
            )}
            <span className="app-header__user-email">{user.email}</span>
            <span>{currentOrganization?.name ?? 'Sin organización actual'}</span>
            <span>{currentRole ?? 'Sin membresía actual'}</span>
          </div>
        )}

        <button
          className="app-header__logout"
          type="button"
          onClick={handleLogout}
        >
          Cerrar sesión
        </button>
      </div>
    </header>
  )
}

export default Header
