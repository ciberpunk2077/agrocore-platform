# AgroCore UI-1A

Base visual aislada. Importar componentes desde `./components`; no aplica estilos a controles antiguos.

Con `npm run dev`, abrir `/ui-demo.html` para revisar ambos temas lado a lado. Es una entrada de desarrollo independiente, sin ruta en el router y sin inclusión en el build productivo actual.

El tema inicial es claro. Para comprobar tokens manualmente: `document.documentElement.dataset.agTheme = 'dark'`. Para restaurar: eliminar ese atributo. Solo los consumidores de tokens cambian; las páginas V1 aún no están migradas. No hay selector ni persistencia.

`Field` recibe un `id` único y una función hija. Pasar sus atributos al control nativo: `<Field id="name" label="Nombre">{attrs => <Input {...attrs} name="name" />}</Field>`. Conserva labels, mensajes y referencias ARIA. Si se necesitan otras descripciones ARIA, combinar sus IDs con los entregados por Field. Los controles aceptan props nativas y ref. Button usa `type="button"` por defecto; indicar `type="submit"` para formularios.

No montar estos componentes automáticamente en módulos existentes. Las clases de tipografía `ag-heading`, `ag-heading--large` y `ag-numeric` son optativas. Sin fuentes externas ni dependencias nuevas.

Pruebas de componentes y contraste de tokens: `node --test src/ui/ui.test.mjs`. Las pruebas estáticas no sustituyen revisión en navegador, teclado, zoom y lectores de pantalla.
