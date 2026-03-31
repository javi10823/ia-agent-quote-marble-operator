# Marble AI Quoting Agent — Operator Panel

AI-powered quoting agent **Valentina** for D'Angelo Marble Workshop.
Internal tool for the operator — FastAPI + Next.js 14 + Claude API.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.12 |
| ORM | SQLAlchemy 2.0 async |
| DB | PostgreSQL |
| PDF | WeasyPrint |
| Excel | openpyxl |
| Blueprints | Pillow + pdf2image |
| Streaming | SSE (Server-Sent Events) |
| Frontend | Next.js 14 + TypeScript |
| Drive | Google Drive API (Service Account) |
| Deploy API | Railway |
| Deploy Web | Vercel |

---

## Production Deploy (Railway + Vercel)

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR_USER/ia-agent-quote-marble-operator.git
git push -u origin main
```

### 2. Google Service Account (for Drive)

1. console.cloud.google.com → new project `dangelo-marble`
2. APIs & Services → Enable → **Google Drive API**
3. Credentials → Create Credentials → **Service Account** → name: `marble-drive-bot`
4. In the service account → Keys → Add Key → JSON → download → save as `service-account.json`
5. In Google Drive: share the `Presupuestos` folder with the service account email (editor)

### 3. Railway — PostgreSQL

1. railway.app → New Project → Empty Project
2. Add Service → Database → **PostgreSQL**
3. Copy `DATABASE_URL` from the Variables tab

### 4. Railway — API

1. Add Service → **GitHub Repo** → select this repo
2. Settings → Root Directory → `api`
3. Railway auto-detects the `Dockerfile`
4. Variables → add:

```
DATABASE_URL=<from PostgreSQL>
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5-20251001
GOOGLE_DRIVE_FOLDER_ID=<root folder ID in Drive>
APP_ENV=production
CORS_ORIGINS=https://YOUR-APP.vercel.app
SECRET_KEY=<long random string>
```

5. Variables → **Secret Files** → upload `service-account.json` at path `/app/service-account.json`
6. Deploy → copy the generated public URL

### 5. Vercel — Web

1. vercel.com → New Project → import from GitHub
2. Root Directory → `web`
3. Environment Variables:

```
NEXT_PUBLIC_API_URL=https://YOUR-URL.railway.app
```

4. Deploy → copy URL

### 6. Update CORS on Railway

In the Railway API service, update:
```
CORS_ORIGINS=https://YOUR-APP.vercel.app
```
Automatic redeploy.

---

## Local Development

### Requirements
- Python 3.12+
- Node.js 18+
- Docker (for local PostgreSQL)

### API

```bash
cd api
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in variables
docker-compose up -d          # starts PostgreSQL
uvicorn app.main:app --reload --port 8000
```

### Web

```bash
cd web
npm install
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                   # runs on localhost:3000
```

> WeasyPrint requires system dependencies for local development.
> Mac: `brew install pango libffi`
> Ubuntu: `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libffi-dev`

---

## Environment Variables

### `api/.env`

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_MODEL` | Model to use (default: claude-sonnet-4-5-20251001) |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to service account JSON |
| `GOOGLE_DRIVE_FOLDER_ID` | Root folder ID in Google Drive |
| `APP_ENV` | `development` or `production` |
| `CORS_ORIGINS` | Frontend URL (e.g., https://your-app.vercel.app) |
| `SECRET_KEY` | Random string for internal security |

### `web/.env.local`

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Backend base URL (no trailing slash) |

---

## Project Structure

```
ia-agent-quote-marble-operator/
├── CLAUDE.md                     → Claude Code instructions
├── README.md                     → this file
├── docker-compose.yml            → local PostgreSQL
│
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── CONTEXT.md                → Valentina agent system prompt
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                 → config, database, static files
│   │   ├── models/quote.py       → Quote model + QuoteStatus enum
│   │   └── modules/
│   │       ├── agent/            → AgentService + SSE router + tools
│   │       └── catalog/          → catalog CRUD with AI validation
│   ├── catalog/                  → 15 JSONs (materials, labor, sinks, etc.)
│   ├── rules/                    → 6 business rules files
│   ├── examples/                 → 34 validated quote examples
│   └── templates/                → HTML for PDF + validated Excel template
│
└── web/
    ├── package.json
    ├── next.config.ts
    ├── tailwind.config.ts
    └── src/
        ├── app/
        │   ├── layout.tsx        → shell with sidebar
        │   ├── globals.css       → dark premium design tokens
        │   ├── page.tsx          → quotes dashboard
        │   ├── quote/[id]/       → chat with Valentina
        │   └── config/           → catalog settings panel
        ├── components/
        │   ├── ui/Sidebar.tsx
        │   └── chat/MessageBubble.tsx
        └── lib/api.ts            → HTTP client + SSE helpers
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/quotes` | List quotes |
| POST | `/api/quotes` | Create new quote |
| GET | `/api/quotes/:id` | Quote detail with history |
| PATCH | `/api/quotes/:id/status` | Update status (draft/validated/sent) |
| POST | `/api/quotes/:id/chat` | Send message (SSE streaming) |
| GET | `/api/catalog` | List catalogs |
| GET | `/api/catalog/:name` | Get catalog contents |
| POST | `/api/catalog/:name/validate` | Validate changes with AI |
| PUT | `/api/catalog/:name` | Save catalog |
| GET | `/files/:path` | Download generated PDF/Excel files |
