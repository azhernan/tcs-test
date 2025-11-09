import psycopg2
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from psycopg2.extras import execute_values

from . import database, models

app = FastAPI(title="TCS Demo API")

# Crear tablas al iniciar (simple para demo; en prod usar Alembic)
models.Base.metadata.create_all(bind=database.engine)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/items/{item_id}/process")
def enqueue(item_id: int):
    from .tasks import process_item  # import perezoso

    task = process_item.delay(item_id)
    return {"task_id": task.id, "enqueued": True}


@app.get("/items/{name}/history")
def price_history(name: str, limit: int = 50):
    conn = psycopg2.connect(
        host="db",
        port=5432,
        dbname="tcsdb",
        user="tcs",
        password="tcs",
    )
    cur = conn.cursor()
    cur.execute(
        """
        SELECT run_ts, price
        FROM item_prices
        WHERE item_name = %s
        ORDER BY run_ts DESC
        LIMIT %s
        """,
        (name, limit),
    )
    data = [{"run_ts": str(ts), "price": float(p)} for ts, p in cur.fetchall()]
    cur.close()
    conn.close()
    if not data:
        raise HTTPException(status_code=404, detail="No history")
    return JSONResponse(data)


@app.get("/items/latest")
def latest_prices():
    import psycopg2

    conn = psycopg2.connect(
        host="db", port=5432, dbname="tcsdb", user="tcs", password="tcs"
    )
    cur = conn.cursor()
    cur.execute(
        """
        WITH latest AS (
          SELECT item_name, price, run_ts,
                 ROW_NUMBER() OVER (PARTITION BY item_name ORDER BY run_ts DESC) rn
          FROM item_prices
        )
        SELECT item_name, price, run_ts
        FROM latest WHERE rn=1
        ORDER BY item_name;
    """
    )
    data = [
        {"name": n, "price": float(p), "run_ts": str(ts)} for n, p, ts in cur.fetchall()
    ]
    cur.close()
    conn.close()
    return {"items": data}


@app.post("/upload-csv")
def upload_csv(file: UploadFile = File(...)):
    import csv
    import io

    import psycopg2

    conn = psycopg2.connect(
        host="db", port=5432, dbname="tcsdb", user="tcs", password="tcs"
    )
    conn.autocommit = True
    cur = conn.cursor()

    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    rows = [(r["name"], r["price"]) for r in reader if r.get("name") and r.get("price")]

    # UPSERT batch
    upsert_sql = """
        INSERT INTO items (name, price) VALUES %s
        ON CONFLICT (name) DO UPDATE SET price = EXCLUDED.price
    """
    execute_values(cur, upsert_sql, rows)

    # Historial batch
    hist_sql = "INSERT INTO item_prices (item_name, price, run_ts) VALUES %s"
    execute_values(cur, hist_sql, rows, template="(%s, %s, NOW())")

    cur.close()
    conn.close()
    return {"rows": len(rows), "status": "ok"}
