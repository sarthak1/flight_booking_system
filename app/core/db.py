from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, JSON, Numeric
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime
from app.core.settings import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    whatsapp_number = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="user")

class Booking(Base):
    __tablename__ = 'bookings'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    source_iata = Column(String, nullable=False)
    dest_iata = Column(String, nullable=False)
    depart_at = Column(DateTime, nullable=False)
    flight_meta = Column(JSON)
    price = Column(Numeric(10,2))
    currency = Column(String, default='INR')
    payment_status = Column(String, default='pending')
    stripe_session_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookings")

class MessageLog(Base):
    __tablename__ = 'message_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    direction = Column(String)  # in/out
    body = Column(String)
    meta = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
