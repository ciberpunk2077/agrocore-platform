import { Link } from 'react-router-dom'
import LotList from '../lots/components/LotList'
import './LotsPage.css'

export default function LotsPage() {
  return <section className="lots-page lot-inventory-page">
    <header><p className="lot-inventory-page__eyebrow">AgroCore · Espacios ganaderos</p><h1>Gestión de lotes</h1><p>Organización y distribución de tus espacios ganaderos</p></header>
    <Link className="lot-inventory-page__back" to="/farms">← Volver a fincas</Link>
    <LotList />
  </section>
}
