"""
This is the entry point of our backend. Run it with:
    uvicorn main:app --reload

It does four jobs now:
  1. Serves the dashboard (the HTML/JS in ../frontend)
  2. Provides an API for bookings (what the Calendar tab reads/writes)
  3. Provides an API for the AI persona (what the "Your AI" tab edits)
  4. Runs the actual AI brain (what the "Test Chat" tab talks to) —
     now powered by Google Gemini instead of Groq/Llama.
"""

import logging
import os
import time
from datetime import datetime

import httpx

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import engine, get_db, Base
import models
import ai_tools

load_dotenv()  # reads .env and loads GEMINI_API_KEY into the environment
gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
GEMINI_MODEL = "gemini-3.5-flash-lite"
# Used automatically if GEMINI_MODEL's rate limit is hit — a different
# model gets its own separate free-tier quota (confirmed by the
# 'quotaDimensions': {'model': ...} field in every 429 error we've seen).
# If this exact model name isn't available on your account, swap it here
# for whatever current Gemini Flash model your API key does have access
# to — nothing else in the code needs to change.
FALLBACK_GEMINI_MODEL = "gemini-2.5-flash"

# Build the Gemini tool declarations once at startup, straight from our
# existing TOOL_SCHEMAS in ai_tools.py — no need to maintain two copies.
# Gemini accepts a plain JSON-schema dict for "parameters" directly.
_GEMINI_TOOL = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name=schema["function"]["name"],
        description=schema["function"]["description"],
        parameters=schema["function"]["parameters"],
    )
    for schema in ai_tools.TOOL_SCHEMAS
])

# This line creates the actual tables in barberbot.db the first time we run.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="BarberBot API")

# Allows the frontend (even if opened separately) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Request/response shapes (Pydantic validates incoming JSON) ----

class BookingIn(BaseModel):
    customer_name: str
    service: str
    appointment_time: datetime
    source: str = "dashboard"


class PersonaIn(BaseModel):
    business_name: str
    tone: str
    system_prompt: str
    business_hours: str = ""


class ServiceIn(BaseModel):
    name: str
    price: float
    duration_minutes: int


class ClientIn(BaseModel):
    name: str
    phone: str
    email: str | None = None
    notes: str | None = None


class ClientUpdateIn(BaseModel):
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class ChatIn(BaseModel):
    message: str


# ---- Bookings (Calendar tab) ----

@app.get("/api/bookings")
def list_bookings(db: Session = Depends(get_db)):
    return db.query(models.Booking).order_by(models.Booking.appointment_time).all()


@app.post("/api/bookings")
def create_booking(booking: BookingIn, db: Session = Depends(get_db)):
    new_booking = models.Booking(**booking.dict())
    db.add(new_booking)
    db.commit()
    db.refresh(new_booking)
    return new_booking


@app.delete("/api/bookings/{booking_id}")
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking.status = "cancelled"
    db.commit()
    return booking


# ---- Services (Settings tab) ----

@app.get("/api/services")
def list_services(db: Session = Depends(get_db)):
    return db.query(models.Service).order_by(models.Service.name).all()


@app.post("/api/services")
def create_service(service: ServiceIn, db: Session = Depends(get_db)):
    new_service = models.Service(**service.dict())
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service


@app.delete("/api/services/{service_id}")
def delete_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    return {"deleted": True}


# ---- Clients (CRM) ----

@app.get("/api/clients")
def list_clients(db: Session = Depends(get_db)):
    return db.query(models.Client).order_by(models.Client.created_at).all()


@app.post("/api/clients")
def create_client(client: ClientIn, db: Session = Depends(get_db)):
    new_client = models.Client(
        name=client.name,
        phone=client.phone,
        email=client.email,
        notes=client.notes,
        created_at=datetime.utcnow(),
    )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    return new_client


@app.delete("/api/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete(client)
    db.commit()
    return {"deleted": True}


@app.patch("/api/clients/{client_id}")
def update_client(client_id: int, client_update: ClientUpdateIn, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if client_update.phone is not None:
        client.phone = client_update.phone
    if client_update.email is not None:
        client.email = client_update.email
    if client_update.notes is not None:
        client.notes = client_update.notes

    db.commit()
    db.refresh(client)
    return client


# ---- AI Persona (Your AI tab) ----

@app.get("/api/persona")
def get_persona(db: Session = Depends(get_db)):
    persona = db.query(models.AIPersona).first()
    if not persona:
        persona = models.AIPersona()
        db.add(persona)
        db.commit()
        db.refresh(persona)
    return persona


@app.post("/api/persona")
def update_persona(persona_in: PersonaIn, db: Session = Depends(get_db)):
    persona = db.query(models.AIPersona).first()
    if not persona:
        persona = models.AIPersona()
        db.add(persona)
    persona.business_name = persona_in.business_name
    persona.tone = persona_in.tone
    persona.system_prompt = persona_in.system_prompt
    persona.business_hours = persona_in.business_hours
    db.commit()
    db.refresh(persona)
    return persona


# ---- The AI brain (Test Chat tab) ----
# Conversation history lives in memory for now — fine for one shop testing
# solo. Once real Telegram/WhatsApp customers exist, this needs to become
# per-customer history stored in the database instead of one shared list.
# Stored as a list of types.Content objects (Gemini's own format), not
# plain dicts — different shape than the old Groq version.
conversation_history: list[types.Content] = []


def _run_tool_calls(function_calls, db):
    """
    Actually executes whatever tools Gemini decided to call, and returns
    a list of function-response Parts to send back — Gemini already
    parses arguments into a real dict (call.args), unlike Groq which
    sent a JSON string we had to parse ourselves.
    """
    response_parts = []
    for call in function_calls:
        function = ai_tools.TOOL_FUNCTIONS[call.name]
        result = function(db=db, **call.args)
        response_parts.append(
            types.Part.from_function_response(name=call.name, response=result)
        )
    return response_parts


def _looks_like_unverified_confirmation(text: str) -> bool:
    """
    Same safety-net idea as before: catches the model claiming success
    in plain words without a real tool call backing it up.
    """
    if not text:
        return False
    lowered = text.lower()
    return (
        "<function" in lowered
        or "booking id" in lowered
        or "you're all booked" in lowered
        or "you're confirmed" in lowered
    )


def _extract_text(response, fallback: str = "Sorry, could you say that again? I didn't quite catch that.") -> str:
    """
    Safe replacement for response.text. The SDK's .text shortcut doesn't
    raise an error when a response mixes text with a non-text part (like
    a stray function_call) — it silently returns just the text portion,
    which can be an EMPTY STRING. An empty string is falsy in JS, so the
    frontend was showing "AI backend not connected yet" for requests that
    actually succeeded — this is what caused the 2nd, no-crash version of
    that bug. This helper makes sure we always send back something real.

    `fallback` lets each call site supply a reply that actually fits its
    situation, instead of every failure defaulting to the same generic
    "say that again" — which reads as if the bot understood nothing, even
    in cases (like a missing booking time) where we know exactly what's
    missing.
    """
    try:
        candidate = response.candidates[0]
        text_parts = [p.text for p in candidate.content.parts if getattr(p, "text", None)]
        combined = "".join(text_parts).strip()
    except (AttributeError, IndexError):
        combined = ""

    if not combined:
        logging.warning("Gemini response had no usable text content: %r", response)
        combined = fallback

    return combined


def _generate_with_retry(*, model, contents, config, max_attempts=2):
    """
    Wraps generate_content with two kinds of resilience:

    1. Network retry — one automatic retry on dropped-connection errors
       (the Aug 12 incident: 'Server disconnected without sending a
       response'), a real transient blip between this machine and
       Google's servers.

    2. Rate-limit fallback — if THIS model's free-tier quota is
       exhausted (429 RESOURCE_EXHAUSTED), immediately retries the same
       request on FALLBACK_GEMINI_MODEL instead, which has its own
       separate quota bucket. No manual "switch back" logic needed:
       every new call still tries `model` (the primary) first, so
       normal service resumes automatically the moment that model's
       quota window resets.
    """
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return gemini_client.models.generate_content(model=model, contents=contents, config=config)
        except httpx.RemoteProtocolError as e:
            last_error = e
            logging.warning("Gemini call failed (attempt %d/%d): %s", attempt, max_attempts, e)
            if attempt < max_attempts:
                time.sleep(1.5)
        except genai_errors.ClientError as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if is_rate_limit and model != FALLBACK_GEMINI_MODEL:
                logging.warning(
                    "Rate limit hit on %s — falling back to %s for this call",
                    model, FALLBACK_GEMINI_MODEL,
                )
                return gemini_client.models.generate_content(
                    model=FALLBACK_GEMINI_MODEL, contents=contents, config=config
                )
            raise
    raise last_error


def _extract_function_calls(response):
    """
    Manual extraction instead of relying on response.function_calls.
    That convenience property returned empty even when the raw content
    clearly contained a real function_call part (Aug 11 incident:
    finish_reason was a clean STOP, the part had a populated
    function_call, but response.function_calls was still falsy — same
    category of bug as the earlier .text issue). Reading parts directly
    sidesteps whatever SDK quirk causes the property to disagree with
    the raw data.
    """
    try:
        parts = response.candidates[0].content.parts
    except (AttributeError, IndexError):
        return []
    return [p.function_call for p in parts if getattr(p, "function_call", None) is not None]


def _finish_reason_name(response) -> str | None:
    try:
        return response.candidates[0].finish_reason.name
    except (AttributeError, IndexError):
        return None


@app.post("/api/chat")
def chat(chat_in: ChatIn, db: Session = Depends(get_db)):
    persona = db.query(models.AIPersona).first()
    if not persona:
        persona = models.AIPersona()
        db.add(persona)
        db.commit()
        db.refresh(persona)

    system_prompt = (
        f"{persona.system_prompt}\n\n"
        f"Business name: {persona.business_name}\n"
        f"Tone: {persona.tone}\n"
        f"Business hours: {persona.business_hours}\n"
        f"Today's date/time is {datetime.now().isoformat()}."
    )

    conversation_history.append(
        types.Content(role="user", parts=[types.Part.from_text(text=chat_in.message)])
    )

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[_GEMINI_TOOL],
        temperature=0.2,
        # We handle tool execution ourselves against our own database —
        # never let the SDK try to auto-call our functions for us.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    # REWRITE (Aug 2026): the old version was a hand-built chain of
    # "first call -> maybe follow-up -> maybe forced retry -> maybe
    # another follow-up", and several of those calls (the follow-ups)
    # were built WITHOUT tools=[_GEMINI_TOOL] in their config, even
    # though conversation_history already contained real function-call
    # turns from earlier in the same request. That mismatch — tool-call
    # context in history, but no tools declared for this specific call —
    # is what caused repeated "response has a function_call part but
    # finish_reason=STOP and no text" failures at different points in a
    # conversation. Every call in this loop now shares the exact same
    # tool-aware config, so the model always has consistent context.
    MAX_TOOL_TURNS = 4

    try:
        final_reply = None

        for _ in range(MAX_TOOL_TURNS):
            response = _generate_with_retry(
                model=GEMINI_MODEL,
                contents=conversation_history,
                config=config,
            )

            if _finish_reason_name(response) == "MALFORMED_FUNCTION_CALL":
                # The model tried to call check_availability or
                # create_booking but didn't have enough valid information
                # to do so — most commonly a vague time ("today", "later")
                # with no exact hour. Don't just apologize — ask for the
                # missing detail directly instead of guessing again.
                final_reply = "What time works best for you today?"
                conversation_history.append(
                    types.Content(role="model", parts=[types.Part.from_text(text=final_reply)])
                )
                break

            function_calls = _extract_function_calls(response)

            if function_calls:
                # Keeping this turn — append it, then execute the tool(s)
                # and loop again. The NEXT call in this same loop will have
                # the tool result in history AND the same tools config, so
                # the model can either respond in plain text or make
                # another tool call (e.g. create_booking, then
                # create_or_update_client).
                conversation_history.append(response.candidates[0].content)
                response_parts = _run_tool_calls(function_calls, db)
                conversation_history.append(types.Content(role="user", parts=response_parts))
                continue

            # No function call this turn. Safety net: don't trust a
            # confident-sounding confirmation unless a real tool call
            # actually backed it up earlier in this exchange.
            candidate_text = _extract_text(response)

            if _looks_like_unverified_confirmation(candidate_text):
                # BUG FIX (Aug 14): this response's content is being
                # discarded, NOT kept — do not append it to history here.
                # Appending it first (the old behavior) left history ending
                # on a model turn, and Gemini's API rejects the next call
                # in that state ("Requests ending with a model turn are
                # not supported") — that was the actual cause of the
                # crash right after phone-number entry. conversation_history
                # still correctly ends on the last real user/tool turn, so
                # this forced call is valid.
                forced_config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[_GEMINI_TOOL],
                    temperature=0.2,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(mode="ANY")
                    ),
                )
                forced = _generate_with_retry(
                    model=GEMINI_MODEL,
                    contents=conversation_history,
                    config=forced_config,
                )
                forced_function_calls = _extract_function_calls(forced)

                if forced_function_calls:
                    conversation_history.append(forced.candidates[0].content)
                    response_parts = _run_tool_calls(forced_function_calls, db)
                    conversation_history.append(types.Content(role="user", parts=response_parts))
                    continue  # loop again for a real, grounded reply
                else:
                    final_reply = "Let me look into that for you — could you repeat what you'd like to book?"
                    conversation_history.append(
                        types.Content(role="model", parts=[types.Part.from_text(text=final_reply)])
                    )
                    break

            # Genuine, trusted final reply — NOW we append it, since we're
            # actually keeping this turn.
            conversation_history.append(response.candidates[0].content)
            final_reply = candidate_text
            break

        else:
            # Exhausted MAX_TOOL_TURNS without ever landing on a plain-text
            # reply — better to say so than to loop silently forever.
            final_reply = "Sorry, I'm having trouble finishing that up — could you try again in a moment?"
            conversation_history.append(
                types.Content(role="model", parts=[types.Part.from_text(text=final_reply)])
            )

        return {"reply": final_reply}

    except Exception:
        logging.exception("Chat turn failed — see traceback above for the real cause")
        final_reply = "Sorry, I hit a hiccup on my end — could you say that again?"
        conversation_history.append(
            types.Content(role="model", parts=[types.Part.from_text(text=final_reply)])
        )
        return {"reply": final_reply}


# ---- Serve the dashboard itself ----
# This makes visiting http://localhost:8000 load the frontend directly.
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")