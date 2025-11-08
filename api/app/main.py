from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from . import crud, database, models, schemas

app = FastAPI(title="TCS Demo API")

# Crear tablas al iniciar (simple para demo; en prod usar Alembic)
models.Base.metadata.create_all(bind=database.engine)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/items", response_model=schemas.ItemOut, status_code=201)
def create(item: schemas.ItemCreate, db: Session = Depends(database.get_db)):
    return crud.create_item(db, item)


@app.get("/items", response_model=list[schemas.ItemOut])
def list_(db: Session = Depends(database.get_db)):
    return crud.list_items(db)


@app.post("/items/{item_id}/process")
def enqueue(item_id: int):
    # Import lazy para que, si falla Celery, no se caiga el startup de la API
    from .tasks import process_item  # <-- import acá adentro

    task = process_item.delay(item_id)
    return {"task_id": task.id, "enqueued": True}
