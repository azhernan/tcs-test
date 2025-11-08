from sqlalchemy.orm import Session

from . import models
from .celery_app import celery
from .database import SessionLocal


@celery.task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def process_item(self, item_id: int) -> str:
    db: Session = SessionLocal()
    try:
        item = db.get(models.Item, item_id)  # ✅ SQLAlchemy 2.0
        if not item:
            return f"item {item_id} not found"
        # Ejemplo de “proceso”
        item.price = float(item.price) * 1.1
        db.commit()
        return f"processed item {item_id}"
    finally:
        db.close()
