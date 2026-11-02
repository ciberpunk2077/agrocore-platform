import { Outlet } from 'react-router-dom'
import { useCallback, useRef, useState } from 'react'

import Header from '../components/navigation/Header'
import Sidebar from '../components/navigation/Sidebar'
import MainScrollManager from './MainScrollManager'
import './AppLayout.css'
import CurrentContextProvider from '../auth/CurrentContextProvider'

function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const closeMenu = useCallback(() => setMenuOpen(false), [])
  return (
    <CurrentContextProvider><div className="app-shell">
      {typeof __AGROCORE_DEMO__ !== 'undefined' && __AGROCORE_DEMO__ && <p className="ag-demo-banner" role="status" style={{ margin: 0, padding: '6px 16px', background: '#fff3cd', color: '#514000' }}>DEMO · Solo lectura</p>}
      <a className="ag-shell-skip" href="#ag-main-content">Saltar al contenido</a>
      <Header menuOpen={menuOpen} onMenuOpen={() => setMenuOpen(true)} menuButtonRef={menuButtonRef} />

      <div className="app-shell__body">
        <Sidebar open={menuOpen} onClose={closeMenu} menuButtonRef={menuButtonRef} />

        <main ref={mainRef} className="app-shell__content" id="ag-main-content" tabIndex={-1}>
          <MainScrollManager mainRef={mainRef} />
          <Outlet />
        </main>
      </div>
    </div></CurrentContextProvider>
  )
}

export default AppLayout
