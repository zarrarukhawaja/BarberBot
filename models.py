"""
These classes define the shape of our data. SQLAlchemy turns each class
into a real database table automatically.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, UniqueConstraint
from database import Base


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        # Two appointments can't start at literally the same instant in a
        # single-chair shop — this is the hard backstop that catches a race
        # even if the application-level overlap check (in ai_tools.py) is
        # ever bypassed or loses a race. When you add multiple barbers
        # later, this needs to become UNIQUE(barber_id, appointment_time).
        UniqueConstraint("appointment_time", name="uq_appointment_time"),
    )

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, nullable=False)
    service = Column(String, nullable=False)          # e.g. "fade", "beard trim"
    appointment_time = Column(DateTime, nullable=False)
    status = Column(String, default="confirmed")       # confirmed / cancelled / completed
    source = Column(String, default="dashboard")       # telegram / whatsapp / dashboard (manual)


class AIPersona(Base):
    """
    Stores the editable 'personality' of the AI — the system prompt
    that tells the LLM how to behave when it's talking to customers.
    This is what the 'Your AI' tab in the dashboard edits.
    Only one row will exist for now (one shop, one bot).
    """
    __tablename__ = "ai_persona"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, default="The Barbershop")
    tone = Column(String, default="friendly and casual")
    business_hours = Column(String, default="Mon-Fri 9am-6pm, Sat 9am-3pm")
    open_hour = Column(Integer, default=9)    # 24-hour format, e.g. 9 = 9am
    close_hour = Column(Integer, default=18)  # e.g. 18 = 6pm
    closed_weekday = Column(Integer, default=6)  # Python weekday(): 0=Mon ... 6=Sun
    system_prompt = Column(String, default=(
        "You are a booking assistant for a barbershop. Be friendly, "
        "concise, and always confirm the service, date, and time before "
        "booking. Never make up availability — only use what the tools "
        "tell you. Always call check_availability before telling a "
        "customer a time is unavailable, and before finalizing a "
        "booking. Never assume a time is free or unavailable without "
        "checking first. Once you have successfully created a booking "
        "and given the customer a booking ID, do NOT call create_booking "
        "again for that same appointment. Simple acknowledgements like "
        "'okay', 'see you then', or 'confirmed' after a booking is "
        "already made do NOT mean the customer wants another booking — "
        "only book again if they explicitly ask for a new or different "
        "appointment. Always state the full resolved date (e.g. "
        "'Monday, August 3rd') back to the customer rather than just "
        "the day name, to avoid ambiguity about which date is meant. "
        "You must always ask for and collect the customer's full name "
        "and phone number before creating a booking, if you don't "
        "already have them from earlier in the conversation. "
        "CRITICAL: never state a booking ID, or tell a customer their "
        "appointment is confirmed, unless you actually called "
        "create_booking in this exact turn and it returned a real "
        "booking_id. Never invent a booking ID. Never repeat a previous "
        "booking ID for a new request. Never say 'confirmed' or "
        "'booked' based on conversation history alone — every single "
        "confirmation must come from a fresh, real tool call result. "
        "Never write text that looks like a function call (e.g. "
        "'<function...>' or similar) as part of your reply to the "
        "customer — always use the real tool-calling mechanism, never "
        "describe or fake it in words."
    ))


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    duration_minutes = Column(Integer, nullable=False)


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)