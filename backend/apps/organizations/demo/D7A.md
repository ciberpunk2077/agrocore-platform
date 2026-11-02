# D7A — Visualizador backend demo separado y de solo lectura

Desde PowerShell, con la identidad Windows autorizada por las ACL D6B:

```
& .\backend\Start-DemoBackend.ps1 -Port 8011
```

Equivalente desde backend:

```
..\.venv\Scripts\python.exe -B -u manage.py serve_demo --settings=config.settings.demo_view --port 8011
```

No usar runserver para este arranque. El comando dedicado enlaza únicamente
127.0.0.1, rechaza 8000/puertos privilegiados y termina si el puerto está ocupado.
No ejecuta migrate, seed, collectstatic, grants, correos o publicación de claves.
No hay autoreloader ni procesos hijos. Ctrl+C libera las conexiones/handles.

Settings separados de local: misma configuración JWT/SECRET_KEY sin exponerla,
DEBUG=False, ALLOWED_HOSTS solo localhost/127.0.0.1, email dummy y caché en memoria.
Destino SQLite fijo del run 93f864fe-0e45-4eaa-9253-79f8f7f88467. Hashes e
identidades D6C-2B.2 se comprueban al importar settings y antes de servir.
Cambios en la copia requieren nueva revisión; no se acepta una ruta arbitraria.
El comando verifica migraciones sin aplicarlas, integridad/FK, recibo, claves ACL,
grant consumido y manifiestos firmados D2/D3/D4 completos; comprueba database_list.

La conexión es URI mode=ro. Se mantienen handles Windows de lectura que impiden
escritura/sustitución de ambos archivos mientras el visualizador está activo:
no ejecutar otros escritores sobre original o demo simultáneamente. Un intento
de SQL mutante en una petición termina el visualizador; no modifica SQLite.
No se desactivan JWT, permisos, tenant scope ni providers. No se registran URLs,
headers o cuerpos de solicitudes en el access log del visualizador.

Rutas existentes para comprobar: /api/docs, /api/openapi.json, /api/auth/login,
/api/common/context, /api/organizations/, /api/dashboard/summary,
/api/dashboard/upcoming-births y /api/animals/. No se inventa un health endpoint.
Usar únicamente credenciales recuperadas del bundle cifrado en memoria mediante
el mecanismo certificado, sin publicarlas ni guardarlas en archivos/terminal.

El frontend conserva VITE_API_BASE_URL (por defecto /api) y el proxy Vite actual
al puerto 8000. D7B deberá dirigir el proxy /api a 127.0.0.1:8011. Una URL absoluta
a otro origen requeriría resolver CORS; D7A no cambia frontend ni añade CORS.
El backend normal conserva settings.local y su base original. Este visualizador
es para lectura: no habilita formularios de escritura en la copia demo.
