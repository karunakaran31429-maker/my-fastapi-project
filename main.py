from fastapi import FastAPI
import models
import database
import routes

# Create the database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="Smart Warehouse API",
    description="Inventory management system with Pandas forecasting and Twilio SMS alerts."
)

# Attach the routes
app.include_router(routes.router)