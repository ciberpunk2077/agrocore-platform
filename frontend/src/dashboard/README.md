# Dashboard Premium

Fuentes: `/dashboard/summary` (siete KPI) y `/dashboard/upcoming-births` (agenda). No se añaden consultas ni se modifica el protocolo de publicación conjunta, cancelación, sesión, tenant o fecha operativa.

- Se conservan todos los campos y valores, incluidos cero, peso decimal en kg y `null` como «Sin datos».
- Donut SVG: activos y otros estados (total menos activos), con leyenda textual y porcentajes redondeados a un decimal. Total cero no dibuja una composición; conteos incompatibles muestran un estado explicativo.
- Agenda: fechas ISO y días calculados con la aritmética civil existente y `business_today`. Ventana inclusiva hoy..hoy+30 provista por el endpoint, sin refiltrado local. Enlaces de lectura a `/animals/:id`.
- Seguimiento: repite únicamente vacunaciones pendientes y nacimientos previstos del resumen. No representa eventos recientes ni tendencias. Accesos de consulta a `/animals`, `/farms` y `/lots`.
- La organización se mantiene visible en el Header global; no se duplica. Se conserva el tema claro local del Dashboard.
- Diseño responsive con KPI adaptativos, paneles en dos columnas cuando caben, y una columna en móvil. No se incorporan dependencias ni escrituras.

Las pruebas cubren la presentación y el protocolo asíncrono. Las comprobaciones visuales con datos sintéticos no sustituyen la revisión autenticada del dataset DEMO.
