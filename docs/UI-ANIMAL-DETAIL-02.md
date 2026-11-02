# UI-ANIMAL-DETAIL-02 — Información general en la navegación

La primera de las siete tarjetas abre la información general en la ruta existente `/animals/:animalId`. Las otras seis conservan `/animals/:animalId/:section` (salud, pesajes, reproduccion, movimientos, produccion e historial). No se crearon rutas ni endpoints adicionales ni se duplicaron los datos de la ficha.

La navegación compartida permanece en `AnimalDetailPage`, que ya renderiza todas esas vistas a partir del catálogo `animalSections`. Las siete tarjetas están disponibles en cada sección una vez validado el animal. Solo una tarjeta tiene `aria-current="page"`; se destaca con fondo verde suave, borde esmeralda y marca superior. Conserva links HTML accesibles y foco visible. La tarjeta general reutiliza un icono vectorial existente sin modificar Dashboard.

Cada enlace conserva el UUID del animal. Los controles existentes de sesión, organización, permisos y modo DEMO siguen intactos. El regreso directo a `/animals` aparece en todas las secciones, junto con el regreso a la ficha cuando corresponde.

Distribución responsive: siete columnas amplias, tres en pantallas intermedias, dos en móviles y una en pantallas estrechas; textos con wrapping y links de regreso flexibles.

Archivos modificados:
- frontend/src/animals/animal-detail.ts
- frontend/src/pages/AnimalDetailPage.tsx
- frontend/src/pages/AnimalDetailPage.css
- frontend/src/animals/animal-detail.test.mjs

Pruebas específicas: 9/9 PASS. La prueba de navegación recorre las siete vistas y comprueba siete enlaces, Información general primero, misma identidad, regreso a ficha y lista, una sola sección activa y ausencia de información general duplicada en las otras vistas. Se mantienen las pruebas de aislamiento, estados vacíos, Timeline y reglas responsive.

Resultados finales: suite frontend 847/847 PASS; lint PASS; build normal PASS; build DEMO PASS. Se mantiene el aviso de bundle superior a 500 kB. Decisión: READY para revisión visual manual. La revisión visual manual en navegador sigue siendo necesaria; las pruebas responsive comprueban reglas CSS y estructura, no capturas.

Sin cambios a backend, bases, JWT, permisos, login o Dashboard; sin migraciones, seeds ni Git.
