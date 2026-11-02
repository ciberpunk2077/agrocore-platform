import { useNavigate } from 'react-router-dom'
import type { RefObject } from 'react'
import ShellIcon from './ShellIcon'

import { clearSession } from '../../auth/session'
import { useCurrentContext } from '../../auth/current-context'
import './Header.css'

function Header({ menuOpen, onMenuOpen, menuButtonRef }: { menuOpen: boolean; onMenuOpen: () => void; menuButtonRef: RefObject<HTMLButtonElement | null> }) {
  const navigate = useNavigate()
  const { currentUser: user, currentOrganization, currentRole } = useCurrentContext()

  const fullName = user
    ? `${user.first_name} ${user.last_name}`.trim()
    : ''
  const initials = [user?.first_name, user?.last_name]
    .map(name => Array.from(name?.trim() || '')[0] ?? '').join('').toLocaleUpperCase('es')

  function handleLogout() {
    clearSession()
    navigate('/login', { replace: true })
  }

  return (
    <header className="app-header">
      <div className="app-header__heading">
        <button ref={menuButtonRef} type="button" className="app-header__menu" aria-label="Abrir menú de navegación" aria-expanded={menuOpen} aria-controls="ag-navigation-drawer" onClick={onMenuOpen}><ShellIcon name="menu" /></button>
        <span className="app-header__organization-icon"><ShellIcon name="farms" /></span>
        <div className="app-header__organization"><span>ORGANIZACIÓN ACTIVA</span><strong title={currentOrganization?.name}>{currentOrganization?.name ?? 'Sin organización actual'}</strong></div>
      </div>

      <div className="app-header__actions">
        {user && (
          <div className="app-header__identity">
          <span className="app-header__avatar" aria-hidden={true}>{initials || <ShellIcon name="user" />}</span>
          <div className="app-header__user">
            {fullName && (
              <span className="app-header__user-name" title={fullName}>{fullName}</span>
            )}
            <span className="app-header__user-email" title={user.email}>{user.email}</span>
            <span className="app-header__role">{currentRole ?? 'Sin membresía actual'}</span>
          </div>
          </div>
        )}

        <button
          className="app-header__logout"
          type="button"
          onClick={handleLogout}
        >
          <ShellIcon name="logout" />
          Cerrar sesión
        </button>
      </div>
    </header>
  )
}

export default Header
