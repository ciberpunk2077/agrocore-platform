import { Link, useParams } from 'react-router-dom'
import LotFormLoader from '../lots/components/LotFormLoader'
import '../lots/lots.css'

function NewLotPage() {
  const { farmId } = useParams<{ farmId: string }>()
  return <section className="lots-page"><h1>Nuevo lote</h1><Link to={farmId ? `/farms/${farmId}` : '/farms'}>← Volver a finca</Link>{farmId ? <LotFormLoader key={farmId} target={{ mode: 'create', id: farmId }} /> : <p>No se proporcionó una finca.</p>}</section>
}

export default NewLotPage
