# Marble AI Quoting Agent — Operator Panel


Agente de presupuestos **Valentina** para D'Angelo Marmolería.  
Herramienta interna para el operador — FastAPI + Next.js 14 + Claude API.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI + Python 3.12 |
| ORM | SQLAlchemy 2.0 async |
| DB | PostgreSQL |
| PDF | WeasyPrint |
| Excel | openpyxl |
| Planos | Pillow + pdf2image |
| Streaming | SSE (Server-Sent Events) |
| Frontend | Next.js 14 + TypeScript |
| Drive | Google Drive API (Service Account) |
| Deploy API | Railway |
| Deploy Web | Vercel |

---

## Deploy en producción (Railway + Vercel)

### 1. Subir a GitHub

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/TU_USUARIO/ia-agent-quote-marble-operator.git
git push -u origin main
```

### 2. Google Service Account (para Drive)

1. console.cloud.google.com → nuevo proyecto `dangelo-marble`
2. APIs & Services → Enable → **Google Drive API**
3. Credentials → Create Credentials → **Service Account** → nombre: `marble-drive-bot`
4. En el service account → Keys → Add Key → JSON → descargar → guardar como `service-account.json`
5. En Google Drive: compartir la carpeta `Presupuestos` con el email del service account (editor)

### 3. Railway — PostgreSQL

1. railway.app → New Project → Empty Project
2. Add Service → Database → **PostgreSQL**
3. Copiar `DATABASE_URL` de la pestaña Variables

### 4. Railway — API

1. Add Service → **GitHub Repo** → seleccionar este repo
2. Settings → Root Directory → `api`
3. Railway detecta el `Dockerfile` automáticamente
4. Variables → agregar:

```
DATABASE_URL=<el de PostgreSQL>
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5-20251001
GOOGLE_DRIVE_FOLDER_ID=<ID de la carpeta raíz en Drive>
APP_ENV=production
CORS_ORIGINS=https://TU-APP.vercel.app
SECRET_KEY=<string aleatorio largo>
```

5. Variables → **Secret Files** → subir `service-account.json` en path `/app/service-account.json`
6. Deploy → copiar la URL pública generada

### 5. Vercel — Web

1. vercel.com → New Project → importar desde GitHub
2. Root Directory → `web`
3. Environment Variables:

```
NEXT_PUBLIC_API_URL=https://TU-URL.railway.app
```

4. Deploy → copiar URL

### 6. Actualizar CORS en Railway

En el servicio API de Railway, actualizar:
```
CORS_ORIGINS=https://TU-APP.vercel.app
```
Redeploy automático.

---

## Desarrollo local

### Requisitos
- Python 3.12+
- Node.js 18+
- Docker (para PostgreSQL local)

### API

```bash
cd api
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # completar variables
docker-compose up -d          # levanta PostgreSQL
uvicorn app.main:app --reload --port 8000
```

### Web

```bash
cd web
npm install
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                   # corre en localhost:3000
```

> ⚠️ Para desarrollo local WeasyPrint requiere dependencias del sistema.  
> En Mac: `brew install pango libffi`  
> En Ubuntu: `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libffi-dev`

---

## Variables de entorno

### `api/.env`

| Variable | Descripción |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) |
| `ANTHROPIC_API_KEY` | API key de Anthropic |
| `ANTHROPIC_MODEL` | Modelo a usar (default: claude-sonnet-4-5-20251001) |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path al JSON de service account |
| `GOOGLE_DRIVE_FOLDER_ID` | ID de la carpeta raíz en Google Drive |
| `APP_ENV` | `development` o `production` |
| `CORS_ORIGINS` | URL del frontend (ej: https://tu-app.vercel.app) |
| `SECRET_KEY` | String aleatorio para seguridad interna |

### `web/.env.local`

| Variable | Descripción |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | URL base del backend (sin slash final) |

---

## Estructura del proyecto

```
ia-agent-quote-marble-operator/
├── CLAUDE.md                     → instrucciones para Claude Code
├── README.md                     → este archivo
├── docker-compose.yml            → PostgreSQL local
│
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── CONTEXT.md                → system prompt del agente Valentina
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                 → config, database, static files
│   │   ├── models/quote.py       → modelo Quote + QuoteStatus enum
│   │   └── modules/
│   │       ├── agent/            → AgentService + SSE router + tools
│   │       └── catalog/          → CRUD de catálogos con validación IA
│   ├── catalog/                  → 15 JSONs (materiales, MO, piletas, etc.)
│   ├── rules/                    → 6 archivos de reglas de negocio
│   ├── examples/                 → 34 ejemplos validados de presupuestos
│   └── templates/                → HTML para PDF + Excel template validado
│
└── web/
    ├── package.json
    ├── next.config.ts
    ├── tailwind.config.ts
    └── src/
        ├── app/
        │   ├── layout.tsx        → shell con sidebar
        │   ├── globals.css       → design tokens dark premium
        │   ├── page.tsx          → dashboard de presupuestos
        │   ├── quote/[id]/       → chat con Valentina
        │   └── config/           → panel de catálogos
        ├── components/
        │   ├── ui/Sidebar.tsx
        │   └── chat/MessageBubble.tsx
        └── lib/api.ts            → cliente HTTP + SSE helpers
```

---

## Endpoints de la API

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/quotes` | Lista de presupuestos |
| POST | `/api/quotes` | Crear nuevo presupuesto |
| GET | `/api/quotes/:id` | Detalle con historial |
| PATCH | `/api/quotes/:id/status` | Cambiar estado (draft/validated/sent) |
| POST | `/api/quotes/:id/chat` | Enviar mensaje (SSE streaming) |
| GET | `/api/catalog` | Lista de catálogos |
| GET | `/api/catalog/:name` | Contenido de un catálogo |
| POST | `/api/catalog/:name/validate` | Validar cambios con IA |
| PUT | `/api/catalog/:name` | Guardar catálogo |
| GET | `/files/:path` | Descarga de PDF/Excel generados |
