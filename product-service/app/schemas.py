# product-service/app/schemas.py
from pydantic import BaseModel, ConfigDict
from pydantic.fields import Field


class ProductSchema(BaseModel):
    name: str
    description: str | None = None
    price: float
    QT: int


class ProductPublic(BaseModel):
    id: int
    name: str
    price: float
    QT: int
    user_id: int
    model_config = ConfigDict(from_attributes=True)


class ProductUpdateSchema(BaseModel):
    name: str | None = Field(None)
    description: str | None = Field(None)
    price: float | None = Field(None)
    QT: int | None = Field(None)


class ProductListResponse(BaseModel):
    products: list[ProductPublic]
    total_count: int