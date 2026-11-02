# UI-ANIMAL-DETAIL-03 — Información general premium

## Alcance

Se rediseñó exclusivamente el contenido de Información general. El encabezado principal, la navegación de siete tarjetas, las rutas, los ámbitos de animal/sesión/organización, las consultas existentes y los permisos permanecen intactos. No se cambió login, Dashboard, backend, bases de datos ni JWT. No se usó Git ni se ejecutaron migraciones o seeds.

## Archivos

Modificados:
- frontend/src/pages/AnimalDetailPage.tsx: delega el contenido al componente de presentación, conservando el encabezado, navegación, carga y aviso de último peso.
- frontend/src/animals/animal-detail.test.mjs: integra el componente real y amplía verificaciones de campos, ausencias y CSS responsive.

Creados:
- frontend/src/animals/components/AnimalGeneralInformation.tsx
- frontend/src/animals/components/AnimalGeneralInformation.css
- docs/UI-ANIMAL-DETAIL-03.md

`AnimalGeneralInformation` es un componente de presentación sin consultas ni estado editable. Su bloque interno `InformationBlock` reutiliza la misma estructura semántica para cada grupo. Se reutilizan iconos existentes sin modificar los componentes del Dashboard.

## Campos conservados y agrupación

| Bloque | Campos |
|---|---|
| Identificación | Nombre, ID interno, especie, raza, estado, arete oficial y arete electrónico |
| Datos biológicos | Sexo, nacimiento, edad, último peso y peso al nacer |
| Ubicación | Finca y lote |
| Filiación | Madre y padre, conservando UUID/referencia histórica/inactivo cuando corresponde |
| Observaciones | Notas, incluidos saltos de línea |

Se conservan los **15 campos** del contenido anterior; especie y estado se incorporan al grupo solicitado (ya estaban en el encabezado). El encabezado conserva también organización y activo/inactivo. No se añade otro resumen con el nombre o identificador repetido en gran tamaño.

Ausencias: **Sin datos**. La edad sigue usando la fecha operativa válida y el último peso sigue usando la consulta ya existente; se conservan el estado de carga y el aviso de consulta fallida/ambigua. El valor cero no se trata como ausencia. El texto se renderiza mediante React, sin interpretar HTML.

El contrato actual `Animal` no contiene una propiedad de foto. Se presenta un icono vectorial acompañado de “Representación ilustrativa”; no se infieren URLs, no se usa fotografía genérica y no se modifica el contrato para añadir una.

## Diseño y accesibilidad

Tarjetas blancas con borde suave, fondo exterior claro, subtarjetas de datos, esquinas redondeadas, iconos esmeralda y una jerarquía de encabezados h2/h3. Los valores se conservan en listas descriptivas dt/dd; se elimina su presentación como tabla de filas. Cada bloque es una sección con nombre accesible. Los iconos son decorativos y no añaden paradas de teclado. No hay controles editables nuevos.

Contrastes calculados de la paleta utilizada: etiquetas #52675d sobre blanco 6.07:1 y sobre #f8fbf9 5.83:1; valores #163c2c sobre #f8fbf9 11.74:1; “Sin datos” #64736c sobre #f8fbf9 4.79:1; iconos #047857 sobre #ecfdf5 5.21:1. Esta comprobación numérica no equivale a una inspección visual en navegador.

Responsive: bloques en dos columnas y tarjeta de identificación ancha; campos de identificación en tres columnas, dos desde 1100 px; bloques apilados y representación compacta desde 760 px; campos en una columna desde 440 px. Se admiten valores largos y notas multilínea sin recorte. El CSS usa exclusivamente clases `animal-overview` y no modifica encabezado, tarjetas de navegación, login o Dashboard.

## Validación

Pruebas específicas: **12/12 PASS**. Comparación explícita de los 15 campos anteriores y los dos campos agrupados adicionales, valores completos una vez por campo, ausencias, estado vacío, carga, cero, texto escapado, iconos accesibles, estructura responsive. Se mantienen las pruebas de siete accesos, selección por animal, rechazo de identidad equivocada y respuestas tardías tras cambiar sesión/organización.

Suite frontend completa: 850/850 PASS. Lint: PASS. Build normal: PASS. Build DEMO: PASS. Permanece el aviso de bundle superior a 500 kB. Decisión: READY para revisión visual manual.

Pendientes: revisión visual manual en escritorio, tablet y móvil. No se ejecutó navegador ni se revisaron capturas; no se afirma validación visual. El modo DEMO sigue siendo de solo lectura mediante los controles existentes.
