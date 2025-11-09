# TCS Demo — FastAPI + PostgreSQL + Airflow + RabbitMQ/Celery

> Proyecto de ejemplo listo simple. Incluye API (FastAPI), base de datos (PostgreSQL), orquestación (Airflow), mensajería (RabbitMQ) y tareas asíncronas (Celery), con persistencia en Docker y hooks de calidad.

## Arquitectura

- **FastAPI**: API HTTP (`/health`, `/items`, `/items/{id}/process`, `/items/{name}/history`, `/items/latest`).
- **PostgreSQL**: `items` (idempotente por `name`) + `item_prices` (histórico).
- **Airflow**: DAG `daily_prices_etl` (UPSERT + histórico) y `cleanup_item_prices` (retención).
- **RabbitMQ + Celery**: tareas asíncronas (procesar item).

## Levantar servicioes

```bash
docker compose up -d db
docker compose up -d --build api rabbitmq worker
docker compose up -d airflow-init
docker compose up -d airflow-webserver airflow-scheduler

---

## ✨ Qué hace
- **API (FastAPI)** expone endpoints REST:
  - `POST /items` — crear items.
  - `POST /items/{id}/process` — encola una tarea Celery para procesar el item.
  - `GET /items/{name}/history` — histórico de precios (append-only).
  - `GET /items/latest` — último precio por item.
- **Airflow**
  - DAG `daily_prices_etl`: genera CSV, transforma con pandas y **UPSERT** en `items`; registra histórico en `item_prices` (idempotente por `name`).
  - DAG `cleanup_item_prices`: retención de histórico (por ejemplo, 30 días).
  - (Opcional) DAG `backup_pg`: backup diario con `pg_dump`.
- **Celery + RabbitMQ**: procesamiento asíncrono de trabajos publicados por la API.
- **PostgreSQL**: base `tcsdb` con tablas `items` e `item_prices` (histórico).
- **Persistencia**: volumen Docker `pgdata` montado en `/var/lib/postgresql/data`.

---

## 🧩 Arquitectura (resumen)

```

[ FastAPI ]  --HTTP-->  (create/process/history)        ┐
     │                               │                  │
     │                     ┌─────────▼─────────┐        │
     └─ publish task  ───► │   RabbitMQ (AMQP) │ ──────►│
                           └─────────▲─────────┘        │
                                     │                  │
                               [ Celery Worker ]  ------┘
                                     │
                                     ▼
                                [ PostgreSQL ]
                           items / item_prices

[ Airflow ]: DAGs diarios (ETL / retención / backup) leyendo/escribiendo en PostgreSQL.

```

---

## 🚀 Levantar el entorno (Docker Compose)

> Requisitos: Docker Desktop (WSL2 en Windows recomendado) y `docker compose`.

```bash

# 1) Base de datos (con volumen persistente)
docker compose up -d db

# 2) API, cola y worker
docker compose up -d --build api rabbitmq worker

# 3) Inicializar Airflow (primera vez)
docker compose up -d airflow-init

# 4) Webserver y Scheduler de Airflow
docker compose up -d airflow-webserver airflow-scheduler
```

### URLs útiles

- **API**: <http://localhost:8000>
- **OpenAPI/Docs**: <http://localhost:8000/docs>
- **Airflow**: <http://localhost:8080>  (usuario/clave por defecto: `admin`/`admin`)
- **RabbitMQ**: <http://localhost:15672>  (`guest`/`guest`)
- **PostgreSQL**: `localhost:5432` (`tcs`/`tcs`, DB `tcsdb`)

---

## 🗂️ Servicios (compose)

- **db** (PostgreSQL 16): volumen **`pgdata:/var/lib/postgresql/data`** para persistencia.
- **api** (FastAPI + Uvicorn): REST + encolado Celery.
- **rabbitmq**: cola de mensajes (AMQP) con UI de administración.
- **worker** (Celery): ejecuta tareas de la cola.
- **airflow-webserver / airflow-scheduler / airflow-init**: orquestación y UI.

> Importante: el script `db-init/01-init.sql` solo corre cuando el datadir está vacío. Una vez inicializada la DB, ya no se vuelve a ejecutar.

---

## 📚 Modelo de datos (simple)

- **items**
  - `id` (PK)
  - `name` (UNIQUE) — idempotencia por nombre
  - `price` (NUMERIC)
- **item_prices** (histórico append-only)
  - `id` (PK), `item_name`, `price`, `run_ts` (timestamp)

---

## 🔌 Endpoints (demo rápida)

```bash
# Health
curl http://localhost:8000/health

# Crear item
curl -X POST http://localhost:8000/items \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"demo\",\"price\":100}"

# Procesar item (reemplaza ID por el que devolvió la creación)
curl -X POST http://localhost:8000/items/ID/process

# Histórico por nombre
curl http://localhost:8000/items/product_0/history

# Últimos precios por item
curl http://localhost:8000/items/latest
```

> En Windows/PowerShell, si un `curl` JSON falla por comillas, usá esta variante:
>
> ```powershell
> curl.exe --% -X POST http://localhost:8000/items -H "Content-Type: application/json" -d "{\"name\":\"demo\",\"price\":100}"
> ```

---

## 🛠️ DAGs de Airflow

### `daily_prices_etl`

- Genera CSV con precios aleatorios, transforma con pandas.
- Carga con **UPSERT** (`ON CONFLICT (name) DO UPDATE`) en `items`.
- Inserta una fila por item en `item_prices` con el `run_ts` de la corrida.
- **Idempotente**: no duplica nombres en `items`; solo actualiza `price`.

### `cleanup_item_prices`

- Retención: borra filas de `item_prices` con `run_ts` anterior a `N` días (ej. 30).
- Configurable por variables de entorno (`RETENTION_DAYS`, `DRY_RUN`).

### `backup_pg` (opcional)

- `pg_dump` diario de `tcsdb` hacia `/opt/airflow/backups` (montar volumen si querés persistir en host).

#### Comandos útiles

```bash
# Disparar ETL manual dos veces (ver idempotencia e histórico)
docker compose exec airflow-webserver airflow dags trigger daily_prices_etl
docker compose exec airflow-webserver airflow dags trigger daily_prices_etl

# Ver logs del scheduler
docker compose logs --tail=120 airflow-scheduler
```

---

## 💾 Persistencia y Backups

### Persistencia

Asegurate de tener en `docker-compose.yml`:

```yaml
services:
  db:
    volumes:
      - ./db-init/01-init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
      - pgdata:/var/lib/postgresql/data   # <- volumen persistente

volumes:
  pgdata:
```

### Backups manuales

```bash
# Dump
docker compose exec db pg_dump -U tcs -d tcsdb > backup_tcsdb.sql

# Restore
cat backup_tcsdb.sql | docker compose exec -T db psql -U tcs -d tcsdb
```

---

## ✅ Calidad y CI

- **pre-commit**: `ruff`, `ruff-format`, `black` sobre el repo.
- **GitHub Actions** (sugerido): lint + build de imagen `api` en cada push/PR.

```bash
pre-commit run --all-files
```

---

## 🧪 Verificaciones rápidas

```bash
# API viva
curl http://localhost:8000/health

# DB sin duplicados por nombre (items)
docker compose exec db psql -U tcs -d tcsdb -c "SELECT COUNT(*) total, COUNT(DISTINCT name) distintos FROM items;"

# Histórico poblado
docker compose exec db psql -U tcs -d tcsdb -c "SELECT item_name, COUNT(*) FROM item_prices GROUP BY item_name ORDER BY item_name;"
```

---

## 🩺 Troubleshooting (Windows / PowerShell / Airflow)

- **`curl` JSON falla** → usar `curl.exe --% ...` o escapar comillas como en ejemplos.
- **`airflow-webserver` no corre** → revisar logs (`docker compose logs airflow-webserver`), errores de import/sintaxis en DAGs, y reiniciar scheduler/webserver.
- **`UNIQUE VIOLATION` en ETL** → confirmar que el `INSERT` usa `ON CONFLICT (name) DO UPDATE`.
- **API 404 en endpoint nuevo** → reconstruir imagen (`docker compose up -d --build api`), la app dentro del contenedor debe recargar código.

---

## 🧑‍💻 Extensiones sugeridas (para seguir)

- **Streamlit** como UI de carga (formulario y upload CSV) llamando a la API.
- **Endpoint `/upload-csv`** para carga masiva con validaciones.
- **Alembic** para versionado de esquema.
- **Despliegue en VM** (Docker Compose + proxy Nginx + HTTPS) o DB gestionada (RDS/Cloud SQL/Supabase).

---

## 📌 Bullets

- Backend **FastAPI** con endpoints de negocio y carga masiva.
- **ETL diario en Airflow** con **UPSERT** e histórico `item_prices`.
- **RabbitMQ + Celery** para procesamiento asíncrono desde la API.
- **Docker Compose** con **PostgreSQL persistente** y healthchecks.
- Calidad con **pre-commit** (ruff/black) y **CI** (GitHub Actions).
- (Opcional) UI **Streamlit** para carga manual y por CSV.
