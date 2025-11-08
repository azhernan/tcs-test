import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

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
def price_history(name: str):
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
        LIMIT 50
        """,
        (name,),
    )
    data = [{"run_ts": str(ts), "price": float(p)} for ts, p in cur.fetchall()]
    cur.close()
    conn.close()
    if not data:
        raise HTTPException(status_code=404, detail="No history")
    return JSONResponse(data)
