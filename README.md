# ia-agent-quote-marble-operator

Agente de presupuestos para D'Angelo Marmolería. Herramienta interna para el operador.

## Estructura

```
ia-agent-quote-marble-operator/
├── api/                    → Backend FastAPI (Python)
│   ├── app/
│   │   ├── modules/
│   │   │   ├── agent/      → Claude API + SSE streaming
│   │   │   ├── documents/  → PDF (WeasyPrint) + Excel (openpyxl)
│   │   │   ├── storage/    → Google Drive upload
│   │   │   └── catalog/    → lectura de JSONs
│   │   ├── models/         → SQLAlchemy models
│   │   └── core/           → config, deps, db
│   ├── catalog/            → JSONs de materiales, MO, piletas
│   ├── rules/              → reglas de negocio (.md)
│   ├── examples/           → ejemplos validados (.md)
│   ├── templates/          → HTML (PDF) + Excel template
│   └── CONTEXT.md          → system prompt del agente
│
└── web/                    → Frontend Next.js 14 (TypeScript)
    └── src/
        ├── app/
        │   ├── page.tsx            → lista de presupuestos
        │   ├── quote/new/          → chat con Valentina
        │   ├── quote/[id]/         → historial
        │   └── config/             → panel catálogo
        └── components/
            ├── chat/               → UI conversacional
            ├── quote/              → resumen y acciones
            └── ui/                 → componentes base
```

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI + Python 3.12 |
| ORM | SQLAlchemy 2.0 async |
| DB | PostgreSQL |
| PDF | WeasyPrint |
| Excel | openpyxl |
| Planos | Pillow + pdf2pic |
| Streaming | SSE (Server-Sent Events) |
| Frontend | Next.js 14 + TypeScript |
| Drive | Google Drive API (Service Account) |
| Deploy API | Railway |
| Deploy Web | Vercel |

## Setup

### API
```bash
cd api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker-compose up -d  # PostgreSQL local
uvicorn app.main:app --reload
```

### Web
```bash
cd web
npm install
cp .env.example .env.local
npm run dev
```

## Variables de entorno

Ver `api/.env.example` y `web/.env.example`
