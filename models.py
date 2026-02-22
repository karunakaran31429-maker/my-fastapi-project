from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    current_stock = Column(Integer, default=0)
    
    orders = relationship("Order", back_populates="item")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id"))
    quantity = Column(Integer)
    date = Column(DateTime, default=datetime.utcnow)

    item = relationship("Item", back_populates="orders")