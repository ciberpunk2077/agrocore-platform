import { Link } from 'react-router-dom'
import LotList from '../lots/components/LotList'

function LotsPage() {
  return <section className="lots-page"><Link to="/farms">← Volver a fincas</Link><h1>Lotes</h1><LotList /></section>
}

export default LotsPage
