# UI-ANIMAL-EDIT-PREVIEW-03 — Reparación de entrega de estilos

## Causa raíz y evidencia

El proceso Vite activo en **127.0.0.1:5174** devolvía HTTP 200 para `/src/pages/AnimalEditPreviewPage.css`, pero su módulo JavaScript contenía `const __vite__css = ""`. El navegador, por tanto, recibía una actualización de estilo vacía. El módulo medía 523 caracteres y no contenía las reglas del grid.

El mismo archivo con `?direct` devolvía las reglas completas (8245 bytes). Un servidor Vite nuevo, sin puerto HTTP y con el mismo archivo, transformó correctamente el CSS. Esto confirma una transformación vacía retenida en la caché del proceso de desarrollo; **no era una ausencia del import ni un desacuerdo de className/selectores**. Tampoco se atribuye el fallo al BOM: la transformación nueva funcionó con el archivo original.

El momento que originó esa caché no se registró. Un guardado por truncado/escritura es una vía compatible con el síntoma, pero no se presenta como hecho observado. Se añadió espera de escritura estable al watcher como prevención de esa carrera.

## Archivos corregidos

- `frontend/vite.config.ts`: `server.watch.awaitWriteFinish` con estabilidad de 300 ms y sondeo de 50 ms. Conserva host, puertos, proxy, restricciones y modos existentes. La modificación provocó la recarga automática de configuración del servidor activo.
- `frontend/src/pages/AnimalEditPreviewPage.css`: normalización a UTF-8 sin BOM mediante sustitución del archivo completo; reglas visuales conservadas. También invalidó el módulo retenido.
- `frontend/src/animals/preview-css.test.mjs`: regresión de transformación CSS e import TSX reales de Vite, con middleware sin servidor HTTP, HMR desactivado y caché temporal aislada.
- `docs/UI-ANIMAL-EDIT-PREVIEW-03.md`: este reporte.

Artefactos de prueba creados: `frontend/preview-artifacts/animal-edit-preview-vite.html`, `css-fixed-desktop.png` y `css-fixed-mobile.png`. Solo contienen datos ficticios. No se cambió el formulario, sus controles, valores, estado ni handlers.

## Importaciones y clases

Se confirmó el import `./AnimalEditPreviewPage.css` de AnimalEditPreviewPage.tsx y su presencia en la transformación TSX. Se revisaron los estilos globales, las reglas previas del formulario, las media queries y la estructura disabled fieldset/layout. El panel lateral ya se renderizaba en AnimalPreviewFields; al faltar el CSS perdía la presentación de columna.

Selectores comprobados en el JSX, CSS transformado y DOM: `animal-edit-preview__header`, `animal-edit-preview__badge`, `animal-preview-icon`, `animal-preview-layout`, `animal-preview-layout__main`, `animal-preview-layout__aside`, `animal-preview-card`, `animal-preview-card__fields` y `animal-edit-preview__footer`.

Después de la corrección, la URL importada por el navegador devuelve un módulo no vacío con tarjetas, media queries y grid 73/27. No se añadió un stylesheet paralelo que ocultase la causa ni se reescribió el formulario.

## Validación en Chrome y Vite real

La prueba de navegador abre por HTTP en **5174** un fixture construido con la página y controles reales y datos ficticios, importando como módulos **el CSS servido por Vite**, junto con index.css, AnimalDetailPage.css y ExpedientSections.css. No se embebe una copia de los estilos de preview. El navegador no usa tokens, credenciales, datos persistentes ni sesión real. Se midió el DOM después de aplicar los módulos CSS y se abrieron las capturas generadas.

Escritorio, viewport medido 1520 px:
- Fondo raíz y tarjetas: `rgb(255, 255, 255)`.
- Encabezado: `display:flex`.
- Distribución: `display:grid`, columnas **1041.7 px / 385.3 px**, aproximadamente 73/27.
- Panel lateral visible.
- Borde de tarjeta: **1 px**.
- Fondo de iconos: `rgb(225, 251, 239)`.
- **15 controles**, todos deshabilitados; Guardar deshabilitado.
- Cuatro módulos de estilo aplicados desde Vite; ancho scroll 1505 px, menor que el viewport.

Móvil, viewport medido 500 px:
- Una sola columna de **443 px**; lateral visible y apilado, también 443 px.
- Fondo blanco, bordes e iconos aplicados.
- 15 controles deshabilitados y Guardar deshabilitado.
- Ancho scroll 485 px, menor que el viewport; sin desbordamiento horizontal.

Se conserva la limitación del navegador headless de este entorno: no se afirma una medición real por debajo de 500 px. Las capturas son una verificación visual real del render y de los estilos recibidos por Vite con datos de prueba; **no son una sesión autenticada en la ruta del animal real**. Esa revisión manual sigue pendiente.

## Pruebas, lint y builds

Regresión nueva: Vite transforma CSS no vacío, contiene los selectores/grid, TSX importa la hoja y el watcher usa escritura estable. La prueba emplea caché temporal propia y no abre puertos ni escribe en bases.

Resultados finales: **865/865 pruebas PASS**, `npm run lint` PASS, `npm run build` PASS y `npm run build:demo` PASS. Ambos builds emiten el aviso de chunk JavaScript superior a 500 kB; no impide compilar. Las pruebas existentes conservan verificación de precarga, permisos, aislamiento, ausencia de escrituras y funcionamiento de la edición normal. No se tocó backend, SQLite, JWT, rutas ni lógica de negocio. Sin migraciones, seeds o Git.

## Decisión

**READY para revisión visual manual.** La reparación se verificó con CSS del servidor activo, estilos computados y capturas reales de Chrome sobre datos ficticios. Falta revisar manualmente la ruta autenticada con el animal seleccionado. No se declara equivalencia visual completa con la maqueta ni una prueba autenticada que no se realizó.
