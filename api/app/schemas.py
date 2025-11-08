from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: float = Field(ge=0)


class ItemOut(ItemCreate):
    id: int


class Config:
    from_attributes = True
