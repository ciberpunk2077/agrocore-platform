# AgroCore UI-1B: revisión manual

El shell usa los tokens UI-1A. Sidebar desktop desde 768 px; drawer nativo por debajo. No hay selector de organización, notificaciones, selector de tema ni persistencia.

Validar con una sesión real en 320, 375, 768, 1024 y 1440 px:

- Dashboard, Animales, Fincas y Lotes; rutas profundas, F5 y atrás/adelante.
- VIEWER y ADMIN: navegación de lectura; restricciones de escritura existentes.
- Nombres de usuario y organización largos: truncado visual, texto completo en DOM y title; cerrar sesión siempre visible.
- Móvil: abrir menú, foco inicial en Cerrar menú, Tab/Shift+Tab dentro del dialog, Escape, cerrar con botón y navegar. Al cerrar, el foco debe volver al disparador. Cambiar a desktop con el drawer abierto.
- Zoom al 200 %, navegación por teclado, enlace Saltar al contenido y lector de pantalla.
- No debe aparecer scroll horizontal de la página. Contenido amplio de módulos antiguos puede desplazarse dentro del área principal.
- Activar manualmente `document.documentElement.dataset.agTheme = 'dark'`: Header, Sidebar y drawer cambian; el área de dominio mantiene fondo claro y color-scheme light. Eliminar el atributo para restaurar.
- Cambio de organización A→B→A por el mecanismo existente: Header/Sidebar deben reflejar el contexto actual sin crear un selector nuevo.

Las pruebas automatizadas comprueban handlers, efectos, semántica, rutas activas con React Router real y estructura CSS. No sustituyen medición del layout, comportamiento nativo de dialog o pruebas con tecnologías de asistencia en navegador.
