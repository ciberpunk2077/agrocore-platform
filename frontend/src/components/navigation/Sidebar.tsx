import { NavLink } from 'react-router-dom'

import { mainNavigation } from '../../app/navigation'
import './Sidebar.css'

function Sidebar() {
  return (
    <aside className="sidebar">
      <nav className="sidebar__nav" aria-label="Navegación principal">
        {mainNavigation.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `sidebar__link${isActive ? ' active' : ''}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

export default Sidebar