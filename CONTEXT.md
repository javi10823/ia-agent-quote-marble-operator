# CONTEXT.md — Resumen del Sistema

**Proyecto:** ia-agent-quote-marble-operator
**Empresa:** D'Angelo Marmoleria (Rosario, Argentina)
**Agente:** Valentina — asistente de presupuestos para marmoleria

---

## Que es este proyecto

Sistema interno para operadores de D'Angelo Marmoleria. El operador describe un trabajo (mesadas, piletas, zocalos, etc.) y el agente Valentina calcula el presupuesto, genera PDF + Excel, y sube los archivos a Google Drive.

---

## Stack

- **Backend:** FastAPI + Python 3.12, SQLAlchemy async, PostgreSQL
- **Frontend:** Next.js 14 + TypeScript + Tailwind CSS
- **IA:** Claude API (streaming SSE) con loop agentico + tools
- **PDF:** WeasyPrint | **Excel:** openpyxl | **Planos:** Pillow + pdf2image
- **Storage:** Google Drive API (Service Account)
- **Deploy:** API en Railway, Web en Vercel, DB en Railway PostgreSQL

---

## Flujo principal

```
Operador escribe brief o adjunta plano
  -> POST /api/quotes/:id/chat (multipart/form-data)
  -> AgentService.stream_chat()
     -> System prompt = CONTEXT.md + rules/*.md + examples/*.md
     -> Claude API streaming + tool use
     -> SSE chunks al frontend

Paso 1: Valentina lista piezas + medidas + m2 (sin precios). Espera confirmacion.
Paso 2: Busca precios, calcula MO, merma, descuentos. Espera confirmacion.
Paso 3: Genera PDF + Excel, sube a Drive, devuelve links.
```

---

## Tools del agente

| Tool | Funcion |
|------|---------|
| `catalog_lookup` / `catalog_batch_lookup` | Busca precios en catalogs/*.json (sin IVA, aplica x1.21) |
| `check_stock` | Verifica retazos disponibles en taller |
| `read_plan` | Rasteriza plano PDF a 300 DPI con Pillow |
| `calculate_quote` | Calcula MO, merma, descuentos, totales (fuente de verdad) |
| `generate_documents` | Genera PDF (WeasyPrint) + Excel (openpyxl), sube a Drive |
| `check_architect` | Verifica si el cliente tiene descuento de arquitecta |
| `patch_quote_mo` | Modifica MO en presupuestos existentes |

---

## Reglas de negocio clave

- **IVA:** todos los catalogos sin IVA. Aplicar x1.21 siempre.
- **USD:** `floor(price x 1.21)` | **ARS:** `round(price x 1.21)`
- **Negro Brasil:** NUNCA merma
- **Merma:** solo sinteticos (Silestone, Dekton, Neolith, Puraprima, Purastone, Laminatto)
- **Johnson:** siempre PEGADOPILETA (empotrada)
- **PEGADOPILETA:** 1 por pileta, no por mesada
- **Zocalos:** ml real de cada lado, default 5cm alto
- **Descuentos:** solo 1 por presupuesto (el mayor %). Solo sobre material, nunca MO.
  - Arquitecta: 5% USD / 8% ARS
  - Edificio: 18% si total m2 > 15
- **Edificios:** sin colocacion, MO /1.05, flete = ceil(piezas/6)
- **Forma de pago:** siempre "Contado"
- **Colocacion:** minimo 1 m2, sobre total incluyendo zocalos

---

## Catalogos (15 JSONs en `api/catalog/`)

| Archivo | Moneda | Contenido |
|---------|--------|-----------|
| materials-granito-nacional.json | ARS | Boreal, Gris Mara, etc. |
| materials-granito-importado.json | USD | Negro Brasil, etc. |
| materials-marmol.json | USD | Carrara, Marquina |
| materials-silestone.json | USD | Cuarzo (placa 4.2 m2) |
| materials-purastone.json | USD | Cuarzo (placa 4.2 m2) |
| materials-dekton.json | USD | Sinterizado (placa 5.12 m2) |
| materials-neolith.json | USD | Sinterizado (placa 5.12 m2) |
| materials-puraprima.json | USD | Sinterizado (placa 5.12 m2) |
| materials-laminatto.json | USD | Sinterizado (placa 5.12 m2) |
| labor.json | ARS | Mano de obra (sin IVA) |
| delivery-zones.json | ARS | Zonas de flete (sin IVA) |
| sinks.json | ARS | Piletas Johnson (sin IVA) |
| architects.json | — | Arquitectas con descuento |
| stock.json | — | Retazos en taller |
| config.json | — | Parametros globales, aliases de material |

---

## Estructura del proyecto

```
ia-agent-quote-marble-operator/
├── api/                        -> FastAPI backend
│   ├── app/
│   │   ├── main.py             -> entry point
│   │   ├── core/               -> config, database, static files
│   │   ├── models/             -> SQLAlchemy models (Quote)
│   │   └── modules/
│   │       ├── agent/
│   │       │   ├── agent.py    -> AgentService: loop agentico + SSE
│   │       │   ├── router.py   -> endpoints REST
│   │       │   └── tools/      -> catalog, plan, document, drive, calculate
│   │       └── catalog/        -> CRUD de catalogos
│   ├── catalog/                -> 15 JSONs de precios
│   ├── rules/                  -> reglas de negocio (.md)
│   ├── examples/               -> 34 ejemplos validados
│   ├── templates/              -> HTML (PDF) + Excel templates
│   └── CONTEXT.md              -> system prompt completo del agente
├── web/                        -> Next.js 14 frontend
│   └── src/
│       ├── app/                -> pages (dashboard, chat, config)
│       ├── components/         -> Sidebar, MessageBubble, etc.
│       └── lib/api.ts          -> cliente HTTP + SSE
└── docker-compose.yml          -> PostgreSQL local
```

---

## Desarrollo local

```bash
# DB
docker-compose up -d

# API (desde api/)
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# Web (desde web/)
npm install
cp .env.example .env.local
npm run dev
```

---

## Deploy

- **API:** Railway (detecta Dockerfile en `api/`)
- **Web:** Vercel (root `web/`, variable `NEXT_PUBLIC_API_URL`)
- **DB:** Railway PostgreSQL (auto-create en primer arranque)

---

## Datos empresa

- **D'Angelo Marmoleria** | San Nicolas 1160, Rosario
- Tel: 341-3082996 | marmoleriadangelo@gmail.com
- Dolar: venta BNA | Forma de pago: "Contado"
- Sena: 80% | Saldo: 20% contra entrega
