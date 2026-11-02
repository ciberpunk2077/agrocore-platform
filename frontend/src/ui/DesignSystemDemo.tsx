import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, LoadingState, Select, Textarea } from './components'
import './demo.css'

export default function DesignSystemDemo() {
  return <main className="ag-demo">
    <h1 className="ag-heading ag-heading--large">AgroCore Platform · UI-1A</h1>
    <p>Demostración aislada. Los controles no realizan operaciones.</p>
    <div className="ag-demo__themes">
      {(['light', 'dark'] as const).map(theme => <section key={theme} data-ag-theme={theme} className="ag-theme-preview" aria-label={`Tema ${theme}`}>
        <h2 className="ag-heading">{theme === 'light' ? 'Tema claro' : 'Tema oscuro'}</h2>
        <Card className="ag-demo__stack">
          <h3 className="ag-heading">Componentes base</h3>
          <div className="ag-demo__row">
            <Button>Principal</Button><Button variant="secondary">Secundario</Button>
            <Button variant="ghost">Discreto</Button><Button variant="danger">Peligro</Button><Button disabled>Deshabilitado</Button>
          </div>
          <div className="ag-demo__row">
            <Badge>Neutral</Badge><Badge tone="success">Correcto</Badge><Badge tone="warning">Atención</Badge><Badge tone="danger">Error</Badge><Badge tone="info">Información</Badge>
          </div>
          <Field id={`${theme}-name`} label="Nombre" hint="Ejemplo de ayuda contextual.">{attrs => <Input {...attrs} name="name" placeholder="Identificación del animal" />}</Field>
          <Field id={`${theme}-invalid`} label="Código" error="Introduce un código válido.">{attrs => <Input {...attrs} required defaultValue="Ejemplo" />}</Field>
          <Field id={`${theme}-select`} label="Selección">{attrs => <Select {...attrs} defaultValue=""><option value="">Selecciona una opción</option><option value="example">Ejemplo</option></Select>}</Field>
          <Field id={`${theme}-notes`} label="Notas">{attrs => <Textarea {...attrs} name="notes" />}</Field>
          <Field id={`${theme}-disabled`} label="Campo deshabilitado">{attrs => <Input {...attrs} disabled defaultValue="Solo demostración" />}</Field>
          <LoadingState /><EmptyState /><ErrorState />
        </Card>
      </section>)}
    </div>
  </main>
}
