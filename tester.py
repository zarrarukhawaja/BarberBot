"""
Automated conversation test for BarberBot's /api/chat endpoint.

Run this while `uvicorn main:app --reload` is running locally. It fires a
sequence of real HTTP requests at the chat endpoint — the same thing as
typing in the Test Chat tab, just scripted — and flags any reply that
looks like a failure, instead of you having to eyeball the chat window.

Usage:
    pip install requests --break-system-packages   # if not already installed
    python3 test_chat_conversation.py

Hand this file to Gemini CLI and ask it to run it (and re-run it after
future changes) instead of manually retesting in the browser each time.

Tip: restart your uvicorn server right before running this, so
conversation_history starts clean — otherwise this test's results get
mixed in with whatever's already piled up from earlier manual testing.
"""

import time

import requests

BASE_URL = "http://127.0.0.1:8000"

# Gemini's free tier caps at 15 requests/minute, and a single chat message
# can trigger 2-4 real API calls internally (tool call -> follow-up,
# sometimes a forced retry). Firing messages back-to-back burns through
# that quota fast and causes real 429 errors that look like random
# failures. This delay keeps the test comfortably under the limit.
DELAY_BETWEEN_MESSAGES_SECONDS = 6

# Phrases that indicate something went wrong, based on every real failure
# we've hit so far in manual testing. Add to this list any time a new
# failure message shows up that isn't caught here yet.
FAILURE_MARKERS = [
    "ai backend not connected",
    "hit a hiccup",
    "didn't quite catch that",
    "having trouble finishing",
]

CONVERSATION = [
    "Hello! What services do you offer?",
    "How much does a Beard Trim cost?",
    "Are you open on Sundays?",
    "Can I book a haircut for tomorrow at 11:00 AM?",
    "My name is Sarah Connor",
    "555-987-6543",
    "Can you check if 2:00 PM tomorrow is open instead?",
    "Great, let's keep the original time then. Thanks!",
    "Where is the shop located?",
]


def run():
    print(f"Testing against {BASE_URL}/api/chat\n")
    failures = []

    for i, message in enumerate(CONVERSATION, start=1):
        try:
            resp = requests.post(f"{BASE_URL}/api/chat", json={"message": message}, timeout=30)
        except requests.exceptions.RequestException as e:
            print(f"[{i}] '{message}' -> REQUEST FAILED: {e}")
            failures.append((message, f"request error: {e}"))
            continue

        if resp.status_code != 200:
            print(f"[{i}] '{message}' -> HTTP {resp.status_code}")
            failures.append((message, f"HTTP {resp.status_code}"))
            continue

        reply = resp.json().get("reply", "")
        lowered = reply.lower()
        is_failure = not reply.strip() or any(marker in lowered for marker in FAILURE_MARKERS)

        status = "FAIL" if is_failure else "ok"
        print(f"[{i}] '{message}'\n    -> ({status}) {reply}\n")

        if is_failure:
            failures.append((message, reply))

        if i < len(CONVERSATION):
            time.sleep(DELAY_BETWEEN_MESSAGES_SECONDS)

    print("=" * 50)
    if failures:
        print(f"{len(failures)} of {len(CONVERSATION)} messages hit a failure marker:")
        for message, reason in failures:
            print(f"  - '{message}': {reason}")
    else:
        print(f"All {len(CONVERSATION)} messages got a clean reply.")


if __name__ == "__main__":
    run()