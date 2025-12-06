# sales-service/app/schemas.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List


class SaleItemSchema(BaseModel):
    product_id: int
    QT: int


class SaleSchema(BaseModel):
    items: list[SaleItemSchema]


class SalePublic(BaseModel):
    id: int
    user_id: int
    total_price: float
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DailySales(BaseModel):
    total_sales: int
    total_amount: float


class SaleItemReport(BaseModel):
    product_name: str
    quantity_sold: int
    sale_date: datetime
    total_price: float


class SalesByPeriodReport(BaseModel):
    sales: List[SaleItemReport]


class BestSellingProduct(BaseModel):
    product_id: int
    product_name: str
    total_quantity_sold: int
    total_revenue: float


class BestSellingProductsReport(BaseModel):
    products: List[BestSellingProduct]