# CLAUDE.md — ia-agent-quote-marble-operator

Agente de presupuestos "Valentina" para D'Angelo Marmolería. Herramienta interna para el operador.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI + Python 3.12 |
| ORM | SQLAlchemy 2.0 async |
| DB | PostgreSQL (Docker Compose dev) |
| PDF | WeasyPrint |
| Excel | openpyxl |
| Planos | Pillow + pdf2image |
| Streaming | SSE (Server-Sent Events) |
| Frontend | Next.js 14 + TypeScript + Tailwind |
| Drive | Google Drive API (Service Account) |
| Deploy API | Railway |
| Deploy Web | Vercel |

---

## Estructura del proyecto

```
ia-agent-quote-marble-operator/
├── api/                          → FastAPI backend
│   ├── app/
│   │   ├── main.py               → entry point, monta routers y static files
│   │   ├── core/
│   │   │   ├── config.py         → Settings (pydantic-settings, lee .env)
│   │   │   ├── database.py       → SQLAlchemy async engine + get_db dependency
│   │   │   └── static.py         → monta /files → api/output/ para descargas
│   │   ├── models/
│   │   │   └── quote.py          → modelo Quote + enum QuoteStatus
│   │   └── modules/
│   │       ├── agent/
│   │       │   ├── agent.py      → AgentService: loop agéntico + SSE streaming
│   │       │   ├── router.py     → endpoints: GET /quotes, POST /quotes, PATCH status, POST chat
│   │       │   ├── schemas.py    → Pydantic schemas de respuesta
│   │       │   └── tools/
│   │       │       ├── catalog_tool.py   → catalog_lookup, check_stock
│   │       │       ├── plan_tool.py      → rasteriza planos a 300 DPI con Pillow
│   │       │       ├── document_tool.py  → genera PDF (WeasyPrint) + Excel (openpyxl)
│   │       │       ├── drive_tool.py     → sube archivos a Google Drive
│   │       │       └── calculate_tool.py → helpers de cálculo (IVA, merma, descuentos)
│   │       └── catalog/
│   │           └── router.py     → GET/PUT /catalog/:name + POST /catalog/:name/validate
│   ├── catalog/                  → 15 JSONs de materiales, MO, piletas, stock, config
│   ├── rules/                    → 6 archivos .md de reglas de negocio
│   ├── examples/                 → 34 ejemplos validados de presupuestos (.md)
│   ├── templates/
│   │   ├── quote-template.html   → template HTML para PDF
│   │   ├── template-structure.md → documentación del formato PDF/Excel
│   │   └── excel/
│   │       └── quote-template-excel.xlsx  → template Excel validado (base para openpyxl)
│   ├── CONTEXT.md                → system prompt del agente Valentina
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
│
├── web/                          → Next.js 14 frontend
│   └── src/
│       ├── app/
│       │   ├── layout.tsx        → shell con Sidebar + Geist font
│       │   ├── globals.css       → design tokens V3 (dark premium)
│       │   ├── page.tsx          → dashboard: lista de presupuestos + KPIs
│       │   ├── quote/[id]/
│       │   │   └── page.tsx      → chat con Valentina + SSE streaming
│       │   └── config/
│       │       └── page.tsx      → panel de catálogos con validación IA
│       ├── components/
│       │   ├── ui/Sidebar.tsx    → sidebar con navegación y CTA único
│       │   └── chat/MessageBubble.tsx  → burbujas por bloques (thinking/text/calc)
│       └── lib/
│           └── api.ts            → cliente HTTP + SSE stream helpers
│
└── docker-compose.yml            → PostgreSQL local para dev
```

---

## Comandos de desarrollo

### Levantar base de datos local
```bash
docker-compose up -d
```

### API (desde `api/`)
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # completar variables
uvicorn app.main:app --reload --port 8000
```

### Web (desde `web/`)
```bash
npm install
cp .env.example .env.local      # completar NEXT_PUBLIC_API_URL
npm run dev                     # corre en localhost:3000
```

---

## Variables de entorno

### `api/.env`
```
DATABASE_URL=postgresql+asyncpg://marble:marble_dev@localhost:5432/marble_operator
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5-20251001
GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
GOOGLE_DRIVE_FOLDER_ID=<id-de-carpeta-raiz-en-drive>
APP_ENV=development
CORS_ORIGINS=http://localhost:3000
SECRET_KEY=<clave-aleatoria>
```

### `web/.env.local`
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Flujo del agente

```
Operador escribe brief / adjunta plano
         ↓
POST /api/quotes/:id/chat (multipart/form-data)
         ↓
AgentService.stream_chat()
  → build_system_prompt() carga CONTEXT.md + rules/*.md + examples/*.md
  → Claude API con streaming + tools
  → SSE chunks → frontend
         ↓
Tools disponibles:
  catalog_lookup    → busca precio en catalog/*.json con IVA aplicado
  check_stock       → verifica retazos disponibles
  read_plan         → rasteriza plano a 300 DPI, crop por mesada
  generate_documents → PDF (WeasyPrint) + Excel (openpyxl)
  upload_to_drive   → sube a Drive en carpeta Presupuestos/YYYY/MM-Mes/
         ↓
Una vez generados: links de descarga en chat + header
```

---

## Reglas de negocio — resumen para el agente

El agente lee `CONTEXT.md` y todos los archivos de `rules/` al inicio de cada conversación. Las reglas más críticas:

- **IVA:** todos los catálogos sin IVA → aplicar ×1.21 siempre
- **USD:** `floor(price × 1.21)` | **ARS:** `round(price × 1.21)`
- **Negro Brasil:** NUNCA merma
- **Merma:** solo sintéticos (Silestone, Dekton, Neolith, Puraprima, Purastone, Laminatto)
- **Johnson:** siempre PEGADOPILETA (empotrada)
- **PEGADOPILETA:** 1 por pileta, no por mesada
- **Zócalos:** ml real de cada lado, default 5cm
- **TOTAL USD/ARS:** misma fila que primera pieza del primer sector
- **Forma de pago:** siempre "Contado"
- **Descuento arquitecta:** 5% sobre material importado
- **Edificios:** sin colocación, MO ÷1.05, flete ceil(piezas/6)

Ver `api/CONTEXT.md` y `api/rules/` para el detalle completo.

---

## Deploy

### API → Railway
1. Conectar repo GitHub a Railway
2. Configurar root directory: `api/`
3. Agregar variables de entorno (ver sección anterior)
4. Subir `service-account.json` como secret file
5. Railway detecta Dockerfile automáticamente

### Web → Vercel
1. Conectar repo GitHub a Vercel
2. Configurar root directory: `web/`
3. Agregar variable: `NEXT_PUBLIC_API_URL=https://<url-railway>`
4. Deploy automático en cada push a main

### Base de datos → Railway PostgreSQL
1. En Railway: Add Service → PostgreSQL
2. Copiar `DATABASE_URL` al servicio de la API
3. La DB se crea automáticamente en el primer arranque (`init_db()`)

---

## Catálogos

Los 15 JSONs en `api/catalog/` son la fuente de verdad de precios. Todos sin IVA.

| Archivo | Moneda | Última actualización |
|---------|--------|---------------------|
| labor.json | ARS | 25/03/2026 |
| delivery-zones.json | ARS | 15/12/2025 |
| materials-granito-nacional.json | ARS | 05/02/2026 |
| materials-purastone.json | USD | 08/01/2026 |
| materials-silestone.json | USD | 04/11/2025 |
| materials-laminatto.json | USD | 02/12/2025 |
| materials-puraprima.json | USD | 29/09/2025 |
| materials-granito-importado.json | USD | 08/09/2025 |
| materials-marmol.json | USD | 08/09/2025 |
| materials-dekton.json | USD | 08/09/2025 |
| materials-neolith.json | USD | 08/09/2025 |
| sinks.json | ARS | 31/10/2025 |
| architects.json | — | 7 arquitectas con descuento |
| stock.json | — | vacío — actualizar con retazos del taller |
| config.json | — | parámetros globales |

⚠️ Catálogos con precios desactualizados (>5 meses): silestone, marmol, granito-importado, dekton, neolith, sinks. Actualizar antes de producción.

---

## Notas para Claude Code

- El agente web **no usa** `pdftoppm`, `present_files`, ni instrucciones de Claude Desktop
- La rasterización de planos la hace `plan_tool.py` con `pdf2image` + `Pillow`
- El loop agéntico está en `agent.py` — loop `while True` con tool use
- El sistema de SSE usa `StreamingResponse` de FastAPI — no WebSockets
- Los archivos generados se sirven desde `/files/` → `api/output/`
- Para agregar una nueva tool: definirla en `TOOLS` list en `agent.py` + implementar en `tools/`
- El `system_prompt` se construye en cada request — carga CONTEXT.md + rules + ejemplos clave
