from sqlalchemy.orm import Session

from . import models, schemas


def create_item(db: Session, item: schemas.ItemCreate) -> models.Item:
    obj = models.Item(name=item.name, price=item.price)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_items(db: Session) -> list[models.Item]:
    return db.query(models.Item).order_by(models.Item.id).all()
