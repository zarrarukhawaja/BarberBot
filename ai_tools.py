"""
This file defines what the AI is *allowed to do* — its "tools."

The LLM never touches the database directly. It only ever sees these
tool *descriptions* and decides "I should call create_booking with
these arguments." Our own Python code then actually runs it.

This separation matters: the AI can decide *when* to book something,
but it physically cannot do anything we haven't explicitly written
a function for here.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import models


# ---- 1. The actual functions (these run for real against the database) ----

def list_services(db: Session):
    services = db.query(models.Service).all()
    return {
        "services": [
            {"name": s.name, "price": s.price, "duration_minutes": s.duration_minutes}
            for s in services
        ]
    }


def _outside_business_hours(db: Session, requested_time: datetime):
    """
    Real, hard-coded check against structured hours — not the free-text
    business_hours field, which the AI can't be trusted to reliably
    enforce on its own. Returns a reason string if closed, or None if open.
    """
    persona = db.query(models.AIPersona).first()
    if not persona:
        return None  # no persona configured yet, don't block bookings

    if requested_time.weekday() == persona.closed_weekday:
        return f"The shop is closed on this day."

    if requested_time.hour < persona.open_hour or requested_time.hour >= persona.close_hour:
        return (
            f"The shop is only open {persona.open_hour}:00 to "
            f"{persona.close_hour}:00. That time is outside business hours."
        )

    return None


def check_availability(db: Session, service: str, appointment_time: str):
    """
    Checks the real database for conflicts at the requested time.
    The AI must call this BEFORE telling a customer a time won't work —
    it should never guess or refuse based on assumption alone.
    """
    requested_time = datetime.fromisoformat(appointment_time)

    hours_issue = _outside_business_hours(db, requested_time)
    if hours_issue:
        return {"available": False, "reason": hours_issue}

    matched_service = db.query(models.Service).filter(models.Service.name.ilike(service)).first()
    duration = matched_service.duration_minutes if matched_service else 30
    requested_end = requested_time + timedelta(minutes=duration)

    existing_bookings = db.query(models.Booking).filter(models.Booking.status != "cancelled").all()

    for existing in existing_bookings:
        existing_service = db.query(models.Service).filter(
            models.Service.name.ilike(existing.service)
        ).first()
        existing_duration = existing_service.duration_minutes if existing_service else 30
        existing_end = existing.appointment_time + timedelta(minutes=existing_duration)

        overlaps = requested_time < existing_end and existing.appointment_time < requested_end
        if overlaps:
            return {
                "available": False,
                "reason": (
                    f"Conflicts with an existing booking from "
                    f"{existing.appointment_time.strftime('%H:%M')} to "
                    f"{existing_end.strftime('%H:%M')}."
                ),
            }

    return {"available": True}


def create_booking(db: Session, customer_name: str, customer_phone: str, service: str, appointment_time: str):
    requested_time = datetime.fromisoformat(appointment_time)

    hours_issue = _outside_business_hours(db, requested_time)
    if hours_issue:
        return {"status": "conflict", "message": hours_issue}

    # Look up the service to know how long this appointment actually takes.
    # If the AI passes a service name that doesn't exist in our list, we
    # default to 30 minutes rather than crashing — better to slightly
    # over-block a slot than to let a booking silently fail.
    matched_service = db.query(models.Service).filter(models.Service.name.ilike(service)).first()
    duration = matched_service.duration_minutes if matched_service else 30
    requested_end = requested_time + timedelta(minutes=duration)

    # Check every existing, non-cancelled booking for a time overlap.
    # Two appointments overlap if one starts before the other ends,
    # in both directions — the classic interval-overlap check.
    existing_bookings = db.query(models.Booking).filter(models.Booking.status != "cancelled").all()

    for existing in existing_bookings:
        existing_service = db.query(models.Service).filter(
            models.Service.name.ilike(existing.service)
        ).first()
        existing_duration = existing_service.duration_minutes if existing_service else 30
        existing_end = existing.appointment_time + timedelta(minutes=existing_duration)

        overlaps = requested_time < existing_end and existing.appointment_time < requested_end
        if overlaps:
            return {
                "status": "conflict",
                "message": (
                    f"That time is not available — there's already a booking "
                    f"from {existing.appointment_time.strftime('%H:%M')} to "
                    f"{existing_end.strftime('%H:%M')} on the same day. "
                    f"Offer the customer a different time."
                ),
            }

    booking = models.Booking(
        customer_name=customer_name,
        service=service,
        appointment_time=requested_time,
        source="test_chat",
    )
    db.add(booking)

    try:
        db.commit()
    except IntegrityError:
        # Backstop for the real race: another request's overlap-check also
        # read "free" before either of us wrote. The UNIQUE constraint on
        # appointment_time catches it here instead of silently creating
        # two bookings for the same instant.
        db.rollback()
        return {
            "status": "conflict",
            "message": (
                "That exact time was just booked by someone else a moment "
                "ago. Offer the customer a nearby time instead."
            ),
        }

    db.refresh(booking)

    # Save/update the client record automatically, every time — this is
    # no longer optional or dependent on the AI remembering a separate
    # tool call. One booking always means one saved contact.
    create_or_update_client(db, name=customer_name, phone=customer_phone)

    return {"status": "booked", "booking_id": booking.id}


def create_or_update_client(db: Session, name: str, phone: str):
    client = db.query(models.Client).filter(models.Client.phone == phone).first()
    if client:
        client.name = name  # keep name up to date
    else:
        client = models.Client(name=name, phone=phone)
        db.add(client)
    db.commit()
    return {"status": "client saved"}


# ---- 2. The schemas — this is what we actually send to the LLM ----
# This format (name/description/parameters as JSON schema) is the
# standard "function calling" shape most LLM providers use, Groq included.

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_services",
            "description": "Get the list of services this barbershop offers, with price and duration. Call this whenever the customer asks what's available, or before booking, to confirm the service exists.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check the real database for whether a specific time is actually free before telling the customer whether it's available or not. You must call this BEFORE saying a time is unavailable — never guess or assume based on the conversation alone. Also call it before confirming a booking, so you can tell the customer up front if a time works.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string"},
                    "appointment_time": {
                        "type": "string",
                        "description": "ISO 8601 format, e.g. 2026-08-05T14:00:00",
                    },
                },
                "required": ["service", "appointment_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": "Book an appointment. Only call this once you have confirmed the customer's name, the exact service, and a specific date/time with the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                    "customer_phone": {"type": "string", "description": "Required. Ask the customer for this if you don't have it yet."},
                    "service": {"type": "string"},
                    "appointment_time": {
                        "type": "string",
                        "description": "ISO 8601 format, e.g. 2026-08-05T14:00:00",
                    },
                },
                "required": ["customer_name", "customer_phone", "service", "appointment_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_or_update_client",
            "description": "Save or update this customer's contact info so we remember them next time. Call this alongside create_booking whenever you learn a customer's name and phone number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                },
                "required": ["name", "phone"],
            },
        },
    },
]

# Maps tool name -> real Python function, so we can call them dynamically
# by whatever name the LLM decides to use.
TOOL_FUNCTIONS = {
    "list_services": list_services,
    "check_availability": check_availability,
    "create_booking": create_booking,
    "create_or_update_client": create_or_update_client,
}