# API Documentation — Marble Operator

Base URL: `https://<api-host>` (Railway) | `http://localhost:8000` (dev)

---

## Autenticacion

Todas las rutas requieren JWT cookie (`auth_token`) salvo las marcadas como publicas.

| Parametro | Valor |
|-----------|-------|
| Mecanismo | JWT en cookie httpOnly |
| Algoritmo | HS256 |
| Expiracion | 72 horas |
| Cookie | `auth_token` |
| SameSite | lax |
| Secure | true (prod), false (dev) |

La API publica (`/api/v1/quote`) usa header `X-API-Key` en lugar de cookie.

---

## Rate Limits

| Endpoint | Limite |
|----------|--------|
| `POST /api/auth/login` | 10 req/min por IP |
| `POST /api/quotes/{id}/chat` | 20 req/min por IP |

---

## Tabla resumen

| Endpoint | Metodo | Auth | Descripcion |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check |
| `/api/auth/login` | POST | No | Login |
| `/api/auth/logout` | POST | Cookie | Logout |
| `/api/auth/create-user` | POST | Condicional | Crear usuario |
| `/api/auth/users` | GET | Cookie | Listar usuarios |
| `/api/auth/users/{id}` | DELETE | Cookie | Eliminar usuario |
| `/api/quotes` | GET | Cookie | Listar presupuestos |
| `/api/quotes` | POST | Cookie | Crear presupuesto |
| `/api/quotes/check` | GET | Cookie | Polling liviano |
| `/api/quotes/{id}` | GET | Cookie | Detalle presupuesto |
| `/api/quotes/{id}` | PATCH | Cookie | Editar campos |
| `/api/quotes/{id}` | DELETE | Cookie | Eliminar presupuesto |
| `/api/quotes/{id}/status` | PATCH | Cookie | Cambiar estado |
| `/api/quotes/{id}/read` | PATCH | Cookie | Marcar como leido |
| `/api/quotes/{id}/chat` | POST | Cookie | Chat SSE streaming |
| `/api/quotes/{id}/validate` | POST | Cookie | Generar docs + validar |
| `/api/quotes/{id}/generate` | POST | Cookie | Generar docs (web) |
| `/api/quotes/{id}/compare` | GET | Cookie | Comparar variantes |
| `/api/quotes/{id}/compare/pdf` | GET | Cookie | PDF comparativo |
| `/files/{path}` | GET | Cookie | Servir archivos generados |
| `/api/catalog/` | GET | Cookie | Listar catalogos |
| `/api/catalog/{name}` | GET | Cookie | Obtener catalogo |
| `/api/catalog/{name}` | PUT | Cookie | Actualizar catalogo |
| `/api/catalog/{name}/validate` | POST | Cookie | Validar catalogo |
| `/api/v1/quote` | POST | API Key | Crear presupuesto (API publica) |
| `/api/v1/quote/{id}/files` | POST | API Key | Subir archivos (API publica) |

---

## 1. Health Check

### `GET /health`

**Auth:** No

**Response 200:**
```json
{
  "status": "ok",
  "service": "marble-operator-api",
  "db": "connected"
}
```

**Response 503:**
```json
{
  "status": "unhealthy",
  "service": "marble-operator-api",
  "db": "unreachable"
}
```

---

## 2. Autenticacion

### `POST /api/auth/login`

**Auth:** No
**Rate Limit:** 10/min por IP

**Request:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response 200:**
```json
{
  "ok": true,
  "username": "string"
}
```
Setea cookie `auth_token` (httpOnly, 72h).

**Error 401:** `{"detail": "Usuario o contrasenya incorrectos"}`

---

### `POST /api/auth/logout`

**Auth:** Cookie

**Response 200:**
```json
{
  "ok": true
}
```
Borra cookie `auth_token`.

---

### `POST /api/auth/create-user`

**Auth:** Sin auth para el primer usuario (setup inicial). Despues requiere cookie.

**Request:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response 200:**
```json
{
  "ok": true,
  "id": "uuid",
  "username": "string"
}
```

**Validaciones:**
- Password minimo 6 caracteres
- Username unico

**Errores:**
- 400: usuario ya existe o password muy corto
- 401: no autenticado (post-setup)

---

### `GET /api/auth/users`

**Auth:** Cookie

**Response 200:**
```json
[
  {
    "id": "uuid",
    "username": "string",
    "created_at": "ISO datetime | null"
  }
]
```

---

### `DELETE /api/auth/users/{user_id}`

**Auth:** Cookie

**Response 200:**
```json
{
  "ok": true
}
```

**Error 400:** `{"detail": "No se puede eliminar el ultimo usuario"}`

---

## 3. Presupuestos

### `GET /api/quotes`

**Auth:** Cookie

**Query params:**

| Param | Tipo | Default | Rango |
|-------|------|---------|-------|
| `limit` | int | 100 | 1-200 |
| `offset` | int | 0 | >= 0 |

**Response 200:**
```json
[
  {
    "id": "uuid",
    "client_name": "string",
    "project": "string",
    "material": "string | null",
    "total_ars": "number | null",
    "total_usd": "number | null",
    "status": "draft | pending | validated | sent",
    "pdf_url": "string | null",
    "excel_url": "string | null",
    "drive_url": "string | null",
    "parent_quote_id": "string | null",
    "source": "operator | web",
    "is_read": true,
    "notes": "string | null",
    "created_at": "ISO datetime"
  }
]
```

**Comportamiento:**
- Excluye borradores vacios (status=draft sin client_name)
- Ordena por `created_at` DESC

---

### `GET /api/quotes/check`

**Auth:** Cookie

**Response 200:**
```json
{
  "count": 5,
  "last_updated_at": "ISO datetime | null"
}
```

Endpoint liviano para polling — detecta cambios sin cargar la lista completa.

---

### `POST /api/quotes`

**Auth:** Cookie

**Request (opcional):**
```json
{
  "status": "draft | pending"
}
```

| Campo | Tipo | Requerido | Default |
|-------|------|-----------|---------|
| `status` | string | No | `"draft"` |

Se puede llamar sin body (backward compatible).

**Response 200:**
```json
{
  "id": "uuid"
}
```

**Ejemplos:**

```bash
# Sin body — crea con status draft
curl -X POST /api/quotes

# Con status explicito
curl -X POST /api/quotes \
  -H "Content-Type: application/json" \
  -d '{"status": "pending"}'
```

---

### `GET /api/quotes/{quote_id}`

**Auth:** Cookie

**Response 200:**
```json
{
  "id": "uuid",
  "client_name": "string",
  "project": "string",
  "material": "string | null",
  "total_ars": "number | null",
  "total_usd": "number | null",
  "status": "draft | pending | validated | sent",
  "pdf_url": "string | null",
  "excel_url": "string | null",
  "drive_url": "string | null",
  "parent_quote_id": "string | null",
  "source": "operator | web",
  "is_read": true,
  "notes": "string | null",
  "created_at": "ISO datetime",
  "messages": [
    {"role": "user | assistant", "content": "string | array"}
  ],
  "quote_breakdown": {
    "client_name": "string",
    "project": "string",
    "date": "string",
    "delivery_days": "string",
    "material_name": "string",
    "material_type": "string",
    "material_m2": 2.5,
    "material_price_unit": 12000,
    "material_price_base": 30000,
    "material_currency": "USD | ARS",
    "material_total": 30000,
    "discount_pct": 5,
    "discount_amount": 1500,
    "merma": {
      "aplica": true,
      "desperdicio": 0.5,
      "sobrante_m2": 1.2,
      "motivo": "Forma compleja"
    },
    "piece_details": [
      {"description": "Mesada cocina", "largo": 2.5, "dim2": 0.65, "m2": 1.625}
    ],
    "sectors": [
      {"label": "Cocina", "pieces": ["Mesada 2.50x0.65"]}
    ],
    "sinks": [
      {"name": "Johnson Simple", "quantity": 1, "unit_price": 50000}
    ],
    "mo_items": [
      {"description": "Corte en escuadra", "quantity": 2, "unit_price": 5000, "base_price": 5000, "total": 10000}
    ],
    "total_ars": 150000,
    "total_usd": 750
  },
  "source_files": [
    {
      "filename": "plano.pdf",
      "type": "application/pdf",
      "size": 524288,
      "url": "/files/uuid/sources/plano.pdf",
      "uploaded_at": "ISO datetime"
    }
  ]
}
```

**Error 404:** `{"detail": "Presupuesto no encontrado"}`

---

### `PATCH /api/quotes/{quote_id}`

**Auth:** Cookie

**Request:**
```json
{
  "client_name": "string | null",
  "project": "string | null",
  "material": "string | null",
  "parent_quote_id": "string | null"
}
```

Todos los campos opcionales. Solo se actualizan los que se envian con valor no-null.

**Response 200:**
```json
{
  "ok": true,
  "updated": ["client_name", "material"]
}
```

---

### `DELETE /api/quotes/{quote_id}`

**Auth:** Cookie

**Response 200:**
```json
{
  "ok": true
}
```

**Comportamiento:**
- Elimina de la DB
- Elimina archivo en Drive (si existe, best-effort)
- Elimina archivos locales en `/output/{quote_id}/`

**Error 404:** `{"detail": "Presupuesto no encontrado"}`

---

### `PATCH /api/quotes/{quote_id}/status`

**Auth:** Cookie

**Request:**
```json
{
  "status": "draft | pending | validated | sent"
}
```

**Transiciones validas:**

| Desde | Hacia |
|-------|-------|
| `draft` | `validated`, `pending` |
| `pending` | `validated`, `draft` |
| `validated` | `sent`, `draft` |
| `sent` | `validated` |

**Response 200:**
```json
{
  "ok": true
}
```

**Error 400:** `{"detail": "Transicion invalida: draft -> sent"}`

---

### `PATCH /api/quotes/{quote_id}/read`

**Auth:** Cookie

Marca el presupuesto como leido (`is_read = true`).

**Response 200:**
```json
{
  "ok": true
}
```

---

### `POST /api/quotes/{quote_id}/validate`

**Auth:** Cookie

Genera PDF + Excel, sube a Drive, y cambia status a `validated`.

**Prerequisito:** el presupuesto debe tener `quote_breakdown` calculado.

**Response 200:**
```json
{
  "ok": true,
  "pdf_url": "/files/{quote_id}/quote.pdf",
  "excel_url": "/files/{quote_id}/quote.xlsx",
  "drive_url": "https://drive.google.com/..."
}
```

**Errores:**
- 404: presupuesto no encontrado
- 400: no hay `quote_breakdown`

---

### `POST /api/quotes/{quote_id}/generate`

**Auth:** Cookie

Igual que `/validate` pero para presupuestos web que ya tienen breakdown pero no documentos.

**Response 200:**
```json
{
  "ok": true,
  "pdf_url": "/files/{quote_id}/quote.pdf",
  "excel_url": "/files/{quote_id}/quote.xlsx",
  "drive_url": "https://drive.google.com/..."
}
```

---

### `GET /api/quotes/{quote_id}/compare`

**Auth:** Cookie

Devuelve el presupuesto raiz + todas las variantes para comparacion.

**Response 200:**
```json
{
  "parent_id": "uuid",
  "client_name": "string",
  "project": "string",
  "quotes": [
    {
      "id": "uuid",
      "material": "string | null",
      "total_ars": "number | null",
      "total_usd": "number | null",
      "status": "draft | pending | validated | sent",
      "pdf_url": "string | null",
      "quote_breakdown": "object | null"
    }
  ]
}
```

**Requisito:** minimo 2 presupuestos para comparar.

**Errores:**
- 404: presupuesto no encontrado / sin variantes

---

### `GET /api/quotes/{quote_id}/compare/pdf`

**Auth:** Cookie

Genera y descarga un PDF comparativo side-by-side de todas las variantes.

**Response:** archivo PDF
**Content-Type:** `application/pdf`
**Filename:** `Comparativo - {client_name}.pdf`

---

### `POST /api/quotes/{quote_id}/chat`

**Auth:** Cookie
**Rate Limit:** 20/min por IP
**Content-Type:** `multipart/form-data`

**Parametros form:**

| Campo | Tipo | Requerido | Descripcion |
|-------|------|-----------|-------------|
| `message` | string | Si | Mensaje del usuario |
| `plan_files` | file[] | No | Archivos adjuntos (max 5) |

**Restricciones de archivos:**
- Tipos: PDF, JPEG, PNG, WEBP
- Tamanio max: 10 MB por archivo
- Cantidad max: 5 por request

**Response:** `text/event-stream` (SSE)

```
data: {"type": "text", "content": "Hola, analizando tu pedido..."}
data: {"type": "text", "content": " voy a buscar el precio."}
data: {"type": "action", "content": "Buscando en catalogo..."}
data: {"type": "done", "content": ""}
```

**Tipos de evento:**

| Tipo | Descripcion |
|------|-------------|
| `text` | Fragmento de respuesta del agente |
| `action` | Tool use en progreso |
| `error` | Error durante el procesamiento |
| `done` | Stream finalizado |

**Headers de response:**
```
Cache-Control: no-cache
X-Accel-Buffering: no
```

**Errores:**
- 400: demasiados archivos, tipo no soportado, archivo muy grande
- 404: presupuesto no encontrado

---

## 4. Archivos generados

### `GET /files/{file_path}`

**Auth:** Cookie

Sirve archivos generados (PDFs, Excel, planos).

**Ejemplo:** `GET /files/{quote_id}/quote.pdf`

**Comportamiento:**
- Resuelve a `/output/{file_path}`
- Valida que el path este dentro de OUTPUT_DIR (previene path traversal)
- Infiere MIME type de la extension

**Errores:**
- 403: intento de path traversal
- 404: archivo no encontrado

---

## 5. Catalogos

### `GET /api/catalog/`

**Auth:** Cookie

**Response 200:**
```json
[
  {
    "name": "labor",
    "item_count": 15,
    "last_updated": "ISO datetime | null",
    "size_kb": 12.5
  }
]
```

**Catalogos disponibles:**
`labor`, `delivery-zones`, `sinks`, `materials-silestone`, `materials-purastone`, `materials-dekton`, `materials-neolith`, `materials-puraprima`, `materials-laminatto`, `materials-granito-nacional`, `materials-granito-importado`, `materials-marmol`, `stock`, `architects`, `config`

---

### `GET /api/catalog/{catalog_name}`

**Auth:** Cookie

**Response 200:** contenido JSON del catalogo (array u objeto)

**Error 404:** catalogo no encontrado

---

### `PUT /api/catalog/{catalog_name}`

**Auth:** Cookie

**Request:**
```json
{
  "content": [...]
}
```

**Response 200:**
```json
{
  "ok": true,
  "catalog": "labor"
}
```

**Comportamiento:**
- Crea backup: `{name}.json.bak`
- Escritura atomica via archivo temporal
- Invalida cache del catalogo
- Invalida cache de config si se actualiza `config`

**Error 403:** catalogo no permitido

---

### `POST /api/catalog/{catalog_name}/validate`

**Auth:** Cookie

**Request:**
```json
{
  "content": [...]
}
```

**Response 200:**
```json
{
  "valid": true,
  "warnings": [
    {
      "type": "warning",
      "sku": "SKU123",
      "message": "price_ars: cambio de 100.00 a 150.00 (50.0%)"
    }
  ],
  "item_count": 20
}
```

**Validaciones:**
- Cada item debe ser un objeto JSON valido
- Detecta cambios de precio >30% (warning, no bloqueante)

---

## 6. API Publica (Quote Engine)

### `POST /api/v1/quote`

**Auth:** Header `X-API-Key`
(En dev, si `QUOTE_API_KEY` no esta seteado, se omite la verificacion)

**Request:**
```json
{
  "client_name": "Juan Perez",
  "project": "Cocina depto 3A",
  "material": "Silestone Blanco Zeus",
  "pieces": [
    {
      "description": "Mesada cocina",
      "largo": 2.5,
      "prof": 0.65,
      "alto": null
    }
  ],
  "localidad": "Rosario",
  "colocacion": true,
  "pileta": "empotrada_johnson",
  "anafe": false,
  "frentin": false,
  "pulido": false,
  "plazo": "30 dias",
  "discount_pct": 0,
  "date": "05/04/2026",
  "conversation": null,
  "notes": "Notas opcionales"
}
```

**Campos:**

| Campo | Tipo | Requerido | Validacion |
|-------|------|-----------|------------|
| `client_name` | string | Si | 1-200 chars |
| `project` | string | No | max 200 chars, default `""` |
| `material` | string o string[] | Si | Nombre de material |
| `pieces` | PieceInput[] | No | Requerido si no hay `notes` |
| `localidad` | string | No | 1-100 chars |
| `colocacion` | bool | No | default false |
| `pileta` | string | No | `empotrada_cliente`, `empotrada_johnson`, `apoyo` |
| `anafe` | bool | No | default false |
| `frentin` | bool | No | default false |
| `pulido` | bool | No | default false |
| `plazo` | string | No | 1-100 chars |
| `discount_pct` | number | No | 0-100 |
| `date` | string | No | DD/MM/YYYY |
| `conversation` | string | No | Conversacion previa |
| `notes` | string | No | Notas adicionales |

**PieceInput:**

| Campo | Tipo | Validacion |
|-------|------|------------|
| `description` | string | Requerido |
| `largo` | float | > 0, <= 20 |
| `prof` | float | > 0, <= 5 |
| `alto` | float | > 0, <= 5 (opcional) |

**Response 200:**
```json
{
  "ok": true,
  "quotes": [
    {
      "quote_id": "web-uuid",
      "material": "Silestone Blanco Zeus",
      "material_m2": 1.625,
      "material_price_unit": 12000,
      "material_currency": "USD",
      "material_total": 19500,
      "mo_items": [
        {"description": "Corte en escuadra", "quantity": 2, "unit_price": 5000, "total": 10000}
      ],
      "total_ars": 150000,
      "total_usd": 750,
      "merma": {
        "aplica": true,
        "desperdicio": 0.5,
        "sobrante_m2": 1.2,
        "motivo": "Material sintetico"
      },
      "discount": {
        "aplica": false,
        "porcentaje": 0,
        "monto": 0
      },
      "pdf_url": null,
      "excel_url": null,
      "drive_url": null
    }
  ]
}
```

**Error:**
```json
{
  "ok": false,
  "error": "Material no encontrado: Silestone Azul"
}
```

**Comportamiento:**
- Crea un presupuesto por cada material en la lista
- Si no hay `pieces`: intenta parsear desde `notes` con Claude; si falla, crea borrador vacio
- Presupuestos con piezas: status `pending`
- Presupuestos sin piezas: status `draft`
- No genera documentos (requiere `POST /validate` manual)

---

### `POST /api/v1/quote/{quote_id}/files`

**Auth:** Header `X-API-Key`
**Content-Type:** `multipart/form-data`

**Form:** `files` (hasta 5 archivos)

**Restricciones:**
- Tipos: PDF, JPEG, PNG, WEBP
- Max: 10 MB por archivo
- Max: 5 archivos por request

**Response 200:**
```json
{
  "ok": true,
  "saved": 2,
  "errors": [],
  "files": [
    {
      "filename": "plano.pdf",
      "type": "application/pdf",
      "size": 524288,
      "url": "/files/web-uuid/sources/plano.pdf",
      "uploaded_at": "ISO datetime"
    }
  ]
}
```

**Comportamiento:**
- Guarda en `/output/{quote_id}/sources/`
- Omite duplicados por filename
- Retorna lista de errores para archivos rechazados

---

## Enums

### QuoteStatus

```
draft -> pending -> validated -> sent
```

Valores: `"draft"`, `"pending"`, `"validated"`, `"sent"`

### PiletaType

Valores: `"empotrada_cliente"`, `"empotrada_johnson"`, `"apoyo"`

### Material Currency

Valores: `"USD"`, `"ARS"`
