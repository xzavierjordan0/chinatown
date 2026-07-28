from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String(50), unique=True, nullable=False, index=True)
    username = Column(String(100))
    usdt_address = Column(String(100))
    btc_address = Column(String(100))
    ltc_address = Column(String(100))
    is_admin = Column(Boolean, default=False)
    balance = Column(Float, default=0.00)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    orders = relationship("Order", back_populates="user")
    payments = relationship("Payment", back_populates="user")

class Card(Base):
    __tablename__ = "cards"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bin = Column(String(10), nullable=False, index=True)        # ✅ Was String(6), now String(10)
    number = Column(String(19), nullable=False)
    expiry = Column(String(10), nullable=False)                  # ✅ Was String(5), now String(10)
    cvv = Column(String(10), nullable=False)                   # ✅ Was String(4), now String(10)
    country = Column(String(2), default="US")
    billing = Column(Boolean, default=False)
    cardholder = Column(String(100))
    billing_address = Column(Text)
    price = Column(Float, nullable=False)
    is_sold = Column(Boolean, default=False)
    checked = Column(Boolean, default=False)                     # ✅ NEW: checked/unchecked status
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    order = relationship("Order", back_populates="card")

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="completed")
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="orders")
    card = relationship("Card", back_populates="order")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    crypto_type = Column(String(10), default="USDT")
    tx_hash = Column(String(100))
    address = Column(String(100))
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="payments")
