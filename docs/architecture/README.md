# AgroCore Platform

## Arquitectura

AgroCore Platform es un ERP Ganadero construido con una arquitectura modular basada en Django.

La filosofía del proyecto es:

- Código desacoplado.
- Multiempresa (Multi Tenant).
- API REST.
- Arquitectura basada en Servicios.
- Separación entre lógica de negocio y acceso a datos.
- Escalable.
- Fácil de mantener.

---

## Estructura

backend/

apps/

accounts/

animals/

catalogs/

common/

farms/

lots/

organizations/

---

Cada módulo contiene:

- models
- api
- selectors
- services
- admin
- migrations

---

## Flujo

Request

↓

JWT Authentication

↓

Context

↓

Endpoint

↓

Service

↓

Selector

↓

Model

↓

Database

---

## Principios

- Fat Services
- Thin Views
- Reutilización
- DRY
- SOLID
- Clean Architecture
