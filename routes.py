from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import pandas as pd
from datetime import datetime, timedelta
import io

import models, schemas, database
from alert import send_sms_alert, send_analytics_sms

router = APIRouter()

def calculate_burn_rate(item_id: int, db: Session) -> float:
    orders = db.query(models.Order).filter(models.Order.item_id == item_id).all()
    if not orders: return 0.0
    df = pd.DataFrame([{"qty": o.quantity, "date": o.date} for o in orders])
    df['date'] = pd.to_datetime(df['date'])
    total_days = (df['date'].max() - df['date'].min()).days + 1
    return round(df['qty'].sum() / total_days, 2)

@router.get("/inventory/", response_model=List[schemas.ItemResponse], tags=["Inventory"])
def view_inventory(db: Session = Depends(database.get_db)):
    return db.query(models.Item).all()

@router.post("/items/", response_model=schemas.ItemResponse, tags=["Inventory"])
def create_item(item: schemas.ItemCreate, db: Session = Depends(database.get_db)):
    if db.query(models.Item).filter(models.Item.name == item.name).first():
        raise HTTPException(status_code=400, detail="Item already exists")
    db_item = models.Item(name=item.name, current_stock=item.current_stock)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.post("/orders/", response_model=schemas.ItemResponse, tags=["Sales"])
def create_order(order: schemas.OrderCreate, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    item = db.query(models.Item).filter(models.Item.id == order.item_id).first()
    if not item or item.current_stock < order.quantity:
        raise HTTPException(status_code=400, detail="Stock issue")
    item.current_stock -= order.quantity
    db.add(models.Order(item_id=order.item_id, quantity=order.quantity))
    db.commit()
    if item.current_stock < 5:
        background_tasks.add_task(send_sms_alert, item.name, item.current_stock)
    return item

@router.get("/analytics/forecast/", response_model=List[schemas.ForecastResponse], tags=["Analytics"])
def get_forecast(background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    items = db.query(models.Item).all()
    forecasts, sms_lines = [], ["Warehouse Analytics Report:"]
    for item in items:
        avg_sales = calculate_burn_rate(item.id, db)
        days = int(item.current_stock / avg_sales) if avg_sales > 0 else 999
        forecasts.append({
            "item_id": item.id, "item_name": item.name, "current_stock": item.current_stock,
            "avg_daily_sales": avg_sales, "days_until_out_of_stock": days,
            "predicted_stockout_date": (datetime.now() + timedelta(days=days)).date(),
            "recommendation": "CRITICAL ORDER!" if days < 7 else "Healthy"
        })
        if days < 7: sms_lines.append(f"- {item.name}: {item.current_stock} left")
    
    # This triggers the Analytics SMS!
    background_tasks.add_task(send_analytics_sms, "\n".join(sms_lines))
    return forecasts