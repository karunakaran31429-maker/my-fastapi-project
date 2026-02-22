from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import pandas as pd
from datetime import datetime, timedelta
import io

import models, schemas, database
from alert import send_sms_alert, send_analytics_sms

router = APIRouter()

# --- HELPER FUNCTIONS ---
def calculate_burn_rate(item_id: int, db: Session) -> float:
    """Uses Pandas to analyze sales data and calculate daily burn rate."""
    orders = db.query(models.Order).filter(models.Order.item_id == item_id).all()
    if not orders:
        return 0.0
    
    data = [{"qty": o.quantity, "date": o.date} for o in orders]
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    
    total_days = (df['date'].max() - df['date'].min()).days + 1
    total_sold = df['qty'].sum()
    
    if total_days == 0: return float(total_sold)
    return round(total_sold / total_days, 2)

# --- API ENDPOINTS ---

@router.get("/inventory/", response_model=List[schemas.ItemResponse], tags=["Inventory"])
def view_inventory(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    """Retrieves all items currently in the inventory."""
    items = db.query(models.Item).offset(skip).limit(limit).all()
    return items

@router.post("/items/", response_model=schemas.ItemResponse, tags=["Inventory"])
def create_item(item: schemas.ItemCreate, db: Session = Depends(database.get_db)):
    """Creates a new item. Prevents adding items with the same name."""
    existing_item = db.query(models.Item).filter(models.Item.name == item.name).first()
    if existing_item:
        raise HTTPException(status_code=400, detail="An item with this name already exists in the inventory.")
    
    db_item = models.Item(name=item.name, current_stock=item.current_stock)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.post("/orders/", response_model=schemas.ItemResponse, tags=["Sales"])
def create_order(order: schemas.OrderCreate, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    """Creates a single outgoing order, decreases stock, and sends SMS if stock is low."""
    item = db.query(models.Item).filter(models.Item.id == order.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.current_stock < order.quantity:
        raise HTTPException(status_code=400, detail="Not enough stock")

    # Atomic Transaction: Update stock and log sale
    item.current_stock -= order.quantity
    new_order = models.Order(item_id=order.item_id, quantity=order.quantity)
    db.add(new_order)
    db.commit()
    db.refresh(item)

    # Trigger Background SMS Alert if stock drops below 5
    if item.current_stock < 5:
        background_tasks.add_task(send_sms_alert, item.name, item.current_stock)

    return item

@router.post("/upload-csv/", tags=["Sales"])
async def upload_csv(background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    """Uploads outgoing sales/orders, decreases stock, and sends SMS if stock gets low."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Must be a CSV file")

    contents = await file.read()
    df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
    processed, errors = 0, []

    for index, row in df.iterrows():
        try:
            item_id = int(row['item_id'])
            quantity = int(row['quantity'])
            
            item = db.query(models.Item).filter(models.Item.id == item_id).first()
            if not item:
                errors.append(f"Row {index}: Item {item_id} not found")
                continue
            
            # Decrease stock for outgoing order
            item.current_stock -= quantity
            new_order = models.Order(item_id=item_id, quantity=quantity)
            db.add(new_order)
            
            # Trigger Background SMS Alert if this CSV row drops stock below 5
            if item.current_stock < 5:
                background_tasks.add_task(send_sms_alert, item.name, item.current_stock)
                
            processed += 1
        except Exception as e:
            errors.append(f"Row {index} Error: {str(e)}")

    db.commit()
    return {"status": "Complete", "processed": processed, "errors": errors}

@router.post("/upload-income-csv/", tags=["Inventory"])
async def upload_income_csv(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    """Uploads incoming stock data from a CSV and increases current stock."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Must be a CSV file")

    contents = await file.read()
    df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
    processed, errors = 0, []

    for index, row in df.iterrows():
        try:
            item_id = int(row['item_id'])
            quantity = int(row['quantity'])
            
            item = db.query(models.Item).filter(models.Item.id == item_id).first()
            if not item:
                errors.append(f"Row {index}: Item {item_id} not found")
                continue
            
            # Increase stock for incoming inventory
            item.current_stock += quantity
            processed += 1
        except Exception as e:
            errors.append(f"Row {index} Error: {str(e)}")

    db.commit()
    return {"status": "Complete", "processed": processed, "errors": errors}

@router.get("/analytics/forecast/", response_model=List[schemas.ForecastResponse], tags=["Analytics"])
def get_forecast(background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    """Gets the forecast for all items in the inventory and sends a Twilio report."""
    items = db.query(models.Item).all()
    forecasts = []
    
    # Start building the text message
    sms_lines = ["Warehouse Analytics Report:"]

    for item in items:
        avg_sales = calculate_burn_rate(item.id, db)
        
        if avg_sales == 0:
            days_remaining = 999
            runout_date = datetime.now().date()
        else:
            days_remaining = int(item.current_stock / avg_sales)
            runout_date = (datetime.now() + timedelta(days=days_remaining)).date()

        recommendation = "CRITICAL ORDER!" if days_remaining < 7 else "Healthy"
        
        forecasts.append({
            "item_id": item.id,
            "item_name": item.name,
            "current_stock": item.current_stock,
            "avg_daily_sales": avg_sales,
            "days_until_out_of_stock": days_remaining,
            "predicted_stockout_date": runout_date,
            "recommendation": recommendation
        })
        
        # Only add CRITICAL items to the text message to save space
        if days_remaining < 7:
             sms_lines.append(f"- {item.name}: {item.current_stock} left ({days_remaining} days)")

    # If no items were critical, send a positive status update
    if len(sms_lines) == 1:
        sms_lines.append("All inventory is currently Healthy!")

    report_text = "\n".join(sms_lines)
    
    # Trigger the Twilio SMS in the background
    background_tasks.add_task(send_analytics_sms, report_text)

    return forecasts

@router.get("/test-sms/", tags=["Analytics"])
def test_twilio_setup():
    """Tests Twilio directly so we can see the exact error in the browser."""
    import os
    from twilio.rest import Client
    from dotenv import load_dotenv
    
    load_dotenv()
    
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_phone = os.getenv("TWILIO_FROM_NUMBER")
    to_phone = os.getenv("MANAGER_PHONE")
    
    # Check if the .env file is actually being read
    if not account_sid:
        return {"Status": "Failed", "Reason": ".env variables are empty. Check file location!"}

    # Attempt to send the message synchronously
    try:
        client = Client(account_sid, auth_token) 
        message = client.messages.create(
            body="Testing direct Twilio connection!",
            from_=from_phone,
            to=to_phone 
        )
        return {"Status": "Success!", "Message_SID": message.sid}
    except Exception as e:
        return {"Status": "Failed", "Twilio_Error": str(e)}