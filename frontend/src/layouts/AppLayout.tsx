import { Outlet } from 'react-router-dom'

import Header from '../components/navigation/Header'
import Sidebar from '../components/navigation/Sidebar'
import './AppLayout.css'

function AppLayout() {
  return (
    <div className="app-shell">
      <Header />

      <div className="app-shell__body">
        <Sidebar />

        <main className="app-shell__content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default AppLayout