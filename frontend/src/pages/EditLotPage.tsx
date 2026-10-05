import { Link, useParams } from 'react-router-dom'
import LotFormLoader from '../lots/components/LotFormLoader'
import '../lots/lots.css'

function EditLotPage() {
  const { lotId } = useParams<{ lotId: string }>()
  return <section className="lots-page"><h1>Editar lote</h1><Link to={lotId ? `/lots/${lotId}` : '/lots'}>← Volver a lote</Link>{lotId ? <LotFormLoader key={lotId} target={{ mode: 'edit', id: lotId }} /> : <p>No se proporcionó un lote.</p>}</section>
}

export default EditLotPage
