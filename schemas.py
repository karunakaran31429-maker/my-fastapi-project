from pydantic import BaseModel
from datetime import date
from typing import Optional

class ItemCreate(BaseModel):
    name: str
    current_stock: int

class OrderCreate(BaseModel):
    item_id: int
    quantity: int

class ItemResponse(BaseModel):
    id: int
    name: str
    current_stock: int
    class Config:
        from_attributes = True

class ForecastResponse(BaseModel):
    item_id: int
    item_name: str
    current_stock: int
    avg_daily_sales: float
    days_until_out_of_stock: int
    predicted_stockout_date: date
    recommendation: str