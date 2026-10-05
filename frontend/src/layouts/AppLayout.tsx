import { Outlet } from 'react-router-dom'

import Header from '../components/navigation/Header'
import Sidebar from '../components/navigation/Sidebar'
import './AppLayout.css'
import CurrentContextProvider from '../auth/CurrentContextProvider'

function AppLayout() {
  return (
    <CurrentContextProvider><div className="app-shell">
      <Header />

      <div className="app-shell__body">
        <Sidebar />

        <main className="app-shell__content">
          <Outlet />
        </main>
      </div>
    </div></CurrentContextProvider>
  )
}

export default AppLayout
