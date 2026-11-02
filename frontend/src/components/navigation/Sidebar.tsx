import { useEffect, useRef, type RefObject } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { mainNavigation } from '../../app/navigation'
import { useCurrentContext } from '../../auth/current-context'
import ShellIcon from './ShellIcon'
import './Sidebar.css'

interface Props {
  open: boolean
  onClose: () => void
  menuButtonRef: RefObject<HTMLButtonElement | null>
}

function Sidebar({ open, onClose, menuButtonRef }: Props) {
  const { currentOrganization, canRead } = useCurrentContext()
  const location = useLocation()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => { onClose() }, [location.key, onClose])
  useEffect(() => {
    const media = window.matchMedia('(min-width: 768px)')
    const resized = () => { if (media.matches) onClose() }
    media.addEventListener('change', resized)
    return () => media.removeEventListener('change', resized)
  }, [onClose])
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !window.matchMedia('(min-width: 768px)').matches) {
      if (!dialog.open) dialog.showModal()
      closeRef.current?.focus()
    } else if (dialog.open) {
      dialog.close()
      menuButtonRef.current?.focus()
    }
  }, [open, menuButtonRef])

  const navigation = <>
    <div className="ag-sidebar__brand"><span className="ag-sidebar__mark"><ShellIcon name="leaf" /></span><span>AgroCore<span className="ag-sidebar__subtitle">Platform</span></span></div>
    <div className="ag-sidebar__organization"><span>Organización</span><strong title={currentOrganization?.name}>{currentOrganization?.name ?? 'Sin organización actual'}</strong></div>
    {canRead && <nav className="ag-sidebar__nav" aria-label="Navegación principal">
      {(['Resumen', 'Inventario'] as const).map(group => <div className="ag-sidebar__group" key={group}>
        <p className="ag-sidebar__group-label">{group}</p>
        {mainNavigation.filter(item => item.group === group).map(item => <NavLink key={item.path} to={item.path} onClick={onClose}
          className={({ isActive }) => `ag-sidebar__link${isActive ? ' ag-sidebar__link--active' : ''}`}>
          <ShellIcon name={item.icon} /><span>{item.label}</span>
        </NavLink>)}
      </div>)}
    </nav>}
  </>

  return <>
    <aside className="ag-sidebar ag-sidebar--desktop">{navigation}</aside>
    <dialog ref={dialogRef} id="ag-navigation-drawer" className="ag-sidebar ag-sidebar--drawer" aria-label="Menú de navegación"
      onCancel={event => { event.preventDefault(); onClose() }} onClose={onClose}
      onClick={event => { if (event.target === event.currentTarget) onClose() }}>
      <button ref={closeRef} className="ag-sidebar__close" type="button" onClick={onClose} aria-label="Cerrar menú"><ShellIcon name="close" /></button>
      {navigation}
    </dialog>
  </>
}

export default Sidebar
