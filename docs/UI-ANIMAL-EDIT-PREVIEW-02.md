# UI-ANIMAL-EDIT-PREVIEW-02 — Rediseño premium según referencia

**READY para revisión visual.** Lint PASS. Builds normal y DEMO PASS. Referencia principal: maqueta adjunta por el usuario. No se afirma equivalencia píxel a píxel.

## Archivos

Modificados:
- frontend/src/pages/AnimalEditPreviewPage.tsx
- frontend/src/pages/AnimalEditPreviewPage.css
- frontend/src/animals/components/form/AnimalForm.tsx
- frontend/src/animals/edit-preview.test.mjs

Creados:
- frontend/src/animals/components/form/AnimalPreviewFields.tsx
- docs/UI-ANIMAL-EDIT-PREVIEW-02.md
- frontend/preview-artifacts/animal-edit-preview.html (fixture visual con datos ficticios)
- frontend/preview-artifacts/desktop.png
- frontend/preview-artifacts/mobile.png

## Composición

Encabezado: lápiz dentro de tarjeta verde clara, título **Editar animal**, identificador/especie/organización obtenidos del animal y contexto, badge ámbar **Vista previa · Solo lectura** y cierre visible con nombre accesible que vuelve al expediente del mismo animal.

Distribución: columna principal de 73 partes y lateral de 27, con mínimo lateral de 240 px para conservar legibilidad. Tarjetas independientes blancas, títulos navy, descripciones secundarias, iconos esmeralda, campos suaves y bordes redondeados. Una columna desde 800 px y campos apilados desde 600 px. El encabezado y los botones se adaptan mediante flex-wrap.

Tarjetas principales:
1. Identificación: ID interno, nombre, aretes oficial y electrónico.
2. Características biológicas: sexo, fecha de nacimiento y peso al nacer.
3. Clasificación: especie, raza y estado.
4. Ubicación y relaciones: finca, lote, madre y padre.
5. Observaciones: notas.

Los **15 campos existentes** se conservan con sus valores reales. AnimalForm genera una sola colección de controles con sus handlers, etiquetas, valores y validaciones. AnimalPreviewFields distribuye esos mismos elementos React por su etiqueta/ID; no reconstruye ni duplica inputs ni lógica de negocio. El modo de edición normal utiliza la misma colección con su guardado existente. La agrupación premium solo se aplica a readOnly.

Panel lateral:
- Fotografía: icono neutro y “Sin fotografía”; el contrato no proporciona URL de foto.
- Estado: status real y activo/inactivo real, sin inferir resultados sanitarios.
- Ubicación actual: nombres reales de finca/lote o Sin datos.
- Sistema: únicamente organización del contexto backend. Se omite esta tarjeta si no hay ese dato.

Barra inferior: aviso azul de solo lectura, enlace Cancelar / Volver al expediente y **Guardar cambios** deshabilitado con type=button. No hay acción de submit vinculada a ese botón. En móvil la barra deja de ser sticky para no tapar el formulario.

## Seguridad y edición normal

El formulario de vista previa permanece en fieldset disabled; handleSubmit retorna antes de construir/enviar payload en readOnly o DEMO. No carga catálogos ni realiza escrituras. Los placeholders Sin datos se aplican únicamente a campos de vista previa; no sustituyen los valores del registro. La página conserva autenticación, canRead, organización activa, validación del animal y descarte de respuestas tardías. No se tocaron rutas, RequireWrite, JWT, permisos o el bloqueo DEMO global.

La edición normal conserva sus catálogos, valores, filtros, validación, PUT y navegación; tiene una prueba específica con servicios simulados que comprueba guardado y rechazo de finca/lote incoherentes. No se escribió en bases persistentes. Sin backend, SQLite, migraciones, seeds, grants, Git ni dependencias nuevas.

## Capturas y comparación

Se generaron y abrieron capturas con Chrome headless de **los componentes reales renderizados con datos ficticios de prueba**, mediante un HTML local sin sesión, API o backend. El fixture usa el formulario completo, sus 15 controles, la página y el CSS reales. No es una captura del flujo autenticado contra datos persistentes.

- Escritorio: 1536 × 1100, comparado visualmente con la referencia adjunta. Se revisaron estructura de dos columnas, tarjetas, iconos, header, badge, lateral y barra inferior.
- Vista estrecha: 500 × 1200, revisada visualmente con campos apilados. Chrome en este entorno impone un viewport mínimo real de 500 px aunque se soliciten 390 px. Se comprobó mediante DOM: innerWidth=500, scrollWidth=485 y raíz=465 (el resto corresponde a márgenes y scrollbar); no se presenta como prueba de viewport real de 390 px. La primera imagen de 390 px recortaba artificialmente ese viewport y fue reemplazada.
- El fallo inicial de GPU dentro del sandbox se resolvió ejecutando el navegador con autorización, perfil aislado y datos ficticios. Los perfiles y diagnósticos se eliminaron; solo se conservan HTML de prueba y capturas.

Para regenerar solo el HTML del fixture y sus pruebas:

```powershell
Set-Location C:\programas\Proyectos\agrocore-platform\frontend
$env:AGROCORE_PREVIEW_CAPTURE = '1'
try { node --test src/animals/edit-preview.test.mjs } finally { Remove-Item Env:AGROCORE_PREVIEW_CAPTURE }
```

Diferencias deliberadas respecto a la imagen: no se incluyen fecha de registro/creación/actualización, autor, color, señales particulares, tipo de animal, propósito o números de registro de progenitores, porque no son campos del contrato actual. Tampoco se añade edad como un campo editable nuevo. La distribución de los campos se adapta a los 15 soportados y no copia valores de la maqueta. La ilustración es vectorial neutra, no una fotografía. Faltan revisión del flujo autenticado y capturas en dispositivos reales de menos de 500 px.

## Pruebas

Suite completa: **864/864 PASS**. Pruebas específicas finales: **6/6 PASS**. Se comprueban los 15 campos y sus valores, cinco tarjetas, contenido lateral, ausencia de metadatos inventados, no duplicación de controles, readonly en ambos modos, guardado normal simulado, retorno con el mismo animal, rechazo por permisos/identidad/tenant y respuestas tardías. El botón visual Guardar tiene type=button y disabled. Se mantienen las pruebas de layout responsive y foco visible.

Lint PASS. Build normal PASS. Build DEMO PASS. Se mantiene el aviso de bundle superior a 500 kB.
