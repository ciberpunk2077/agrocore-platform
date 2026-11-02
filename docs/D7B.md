# D7B — Frontend DEMO de solo lectura

Decisión: **NOT READY para cerrar la validación visual completa**. El arranque y las lecturas HTTP están preparados y verificados; falta inspección manual en navegador y el frontend existente no dispone de vista Timeline ni selector de organización. No se añadieron esas funcionalidades.

## Arranque PowerShell

Terminal 1, desde la raíz del repositorio y con la identidad Windows autorizada por D6B:

```powershell
Set-Location C:\programas\Proyectos\agrocore-platform
& .\backend\Start-DemoBackend.ps1 -Port 8011
```

Terminal 2:

```powershell
Set-Location C:\programas\Proyectos\agrocore-platform\frontend
npm run dev:demo
```

Abrir `http://127.0.0.1:5174`. Ambos servidores permanecen en loopback. El puerto 5174 es estricto: si está ocupado se rechaza el arranque. Vite rechaza overrides de host/puerto. Iniciar primero el backend; sin él Vite termina con error. Usar Ctrl+C en ambas terminales para detenerlos. Los procesos usados en esta verificación se detuvieron.

## Configuración y sesión

- Modo normal: `npm run dev`, proxy `/api` a `http://127.0.0.1:8000`, claves de sesión habituales y build `dist`.
- Modo DEMO: `--mode demo`, proxy fijo `/api` a `http://127.0.0.1:8011`, host 127.0.0.1, puerto 5174, build `dist-demo`. No necesita modificar archivos .env.
- En DEMO se rechazan VITE_API_BASE_URL distinto de /api y DEMO_API_TARGET distinto del destino fijo. No hay fallback a 8000. La comprobación de disponibilidad usa el OpenAPI existente, sin inventar un endpoint.
- `npm run build:demo` compila sin necesitar servidor. La salida requiere el proxy local; no publicar ni servir con un proxy normal. Preview DEMO se rechaza: usar el arranque dedicado.
- JWT sigue pasando por el cliente HTTP existente y los permisos backend permanecen intactos. Sesión DEMO en `agrocore.demo.*`; normal en `agrocore.*`. El origen 5174 también separa localStorage. Las lecturas DEMO usan no-store.
- Cerrar sesión e iniciar con la cuenta del otro rancho para cambiar de organización. La UI actual no ofrece selector. No se agrega uno en esta fase.
- Obtener credenciales mediante el mecanismo certificado de entrega; no imprimirlas ni guardarlas en archivos o historial. No se incluyen credenciales en este reporte.
- Banner discreto `DEMO · Solo lectura`. canWrite queda restringido en DEMO: WriteOnly oculta acciones y RequireWrite impide acceder a rutas de formularios. El cliente bloquea métodos mutantes antes de fetch, salvo el POST exacto de login. El middleware Vite también rechaza métodos mutantes bajo /api salvo ese login. No se desactiva ninguna validación backend.

## Reporte de verificación

| Campo | Resultado |
|---|---|
| Archivos modificados | frontend/vite.config.ts; frontend/package.json; frontend/src/auth/session.ts; frontend/src/auth/current-context.ts; frontend/src/lib/api.ts; frontend/src/main.tsx |
| Archivos creados | frontend/src/demo.d.ts; frontend/src/demo.test.mjs; frontend/scripts/test.mjs; scripts/verify-d7b.py; docs/D7B.md |
| Configuración Vite | Proxy real comprobado mediante /api/openapi.json a través de 5174; normal 8000 y DEMO 8011 comprobados con resolveConfig |
| Puertos | Backend 127.0.0.1:8011; frontend DEMO 127.0.0.1:5174; normal conserva su configuración |
| Login | 30/30 logins por el proxy; secretos descifrados únicamente en memoria mediante _read_bundle certificado |
| Dashboard | summary y upcoming-births HTTP 200 para las 30 cuentas |
| Organizaciones | Listado y contexto HTTP 200; cinco organizaciones comprobadas |
| Animales | HTTP 200; ranchos con 30, 50, 65, 80 y 100 animales, conjuntos disjuntos |
| Fincas/lotes | Listados HTTP 200 para las 30 cuentas |
| Reproducción/partos | Historiales de breeding, pregnancies y births HTTP 200 para un animal por cuenta |
| Producción | Historial HTTP 200 para un animal por cuenta |
| Timeline | Endpoint HTTP 200 para un animal por cuenta; no hay vista ni ruta frontend conectada |
| Permisos | Contexto y rol verificados: 5 OWNER, 5 ADMIN, 5 VETERINARIAN, 10 OPERATOR, 5 VIEWER; no se enviaron escrituras de negocio para probar permisos |
| Acciones de escritura | Prueba de cliente confirma cero fetch mutantes; DELETE por proxy respondió 405 sin alcanzar Django; controles UI restringidos mediante canWrite |
| Aislamiento | Contexto coincide con organización de cada credencial; inventarios consistentes por rancho; 30/30 accesos a animal ajeno rechazados 403/404 |
| Pruebas frontend | 832/832 pruebas existentes PASS; 2/2 pruebas nuevas DEMO PASS, ejecutadas aparte; sin bases persistentes |
| Build | DEMO PASS; normal PASS; aviso de bundle mayor de 500 kB |
| Django check | PASS con config.settings.demo_view, sin migraciones |
| Rechazo de configuración | Destino 8000 rechazado; backend ausente rechazado después de detener el backend certificado |
| Validación visual | Pendiente: no se ejecutó navegador automatizado ni se inspeccionaron capturas; HTTP 200 no certifica presentación ni todos los detalles |

Hash original SHA256 antes y después:
`7726ad14f1d855cfc0ee9a2a0a8c2039c4cc84b2e885b7f0cbc78317f9d0f2a0`

Hash copia SHA256 antes y después:
`aa4a77d2e9cdf8f8e72fafa42efb7ff2bdc2bae79efdd4f916f68872eeaebd2e`

Para repetir únicamente la comprobación HTTP con ambos servidores activos:

```powershell
Set-Location C:\programas\Proyectos\agrocore-platform
& .\.venv\Scripts\python.exe -B .\scripts\verify-d7b.py
```

El script lee el bundle certificado y mantiene contraseñas y tokens en memoria; imprime solo conteos y estados. No genera datos, grants ni migraciones. Requiere acceso ACL a los artefactos certificados; no modificar permisos para eludir un rechazo.

Para repetir pruebas y compilación:

```powershell
Set-Location C:\programas\Proyectos\agrocore-platform\frontend
npm test
npm run build:demo
npm run lint
```

Incidencias: acceso a artefactos protegidos requirió ejecución autorizada fuera del sandbox; no se modificaron ACL. Sin endpoints faltantes en las lecturas ensayadas. Timeline visual ausente y cambio de rancho mediante nuevo login. No se introdujeron datos ficticios. No se usó Git, ni se modificaron settings, modelos o servicios backend. No se reutiliza aquí el resultado histórico 1033/1033 como prueba nueva.
