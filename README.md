# BarberBot

AI booking assistant for barbershops. See `barber-ai-saas-plan.md` (shared separately) for the full roadmap.

## Structure
```
barberbot/
├── backend/          # FastAPI server — the actual logic and database
│   ├── main.py        # entry point, API routes
│   ├── models.py       # database table definitions
│   ├── database.py     # database connection setup
│   └── requirements.txt
├── frontend/          # The dashboard (Calendar / Your AI / Settings tabs)
│   ├── index.html
│   ├── style.css
│   └── app.js
└── .gitignore
```

## How to run it (do this today)

1. Install Python 3.10+ if you don't have it.
2. Open a terminal in the `backend` folder:
   ```
   cd backend
   python -m venv venv
   ```
3. Activate the virtual environment (keeps this project's packages separate from everything else on your machine):
   - Mac/Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`
4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
5. Run the server:
   ```
   uvicorn main:app --reload
   ```
6. Open your browser to `http://localhost:8000` — you should see the dashboard, with Calendar, Your AI, and Settings tabs.

A file called `barberbot.db` will appear in `backend/` the first time you run it — that's your entire database, a single file, nothing else to install.

## What's real right now vs. what's next
**Working today:** the dashboard, a real database, an editable AI persona (though nothing reads it yet), manual booking storage via the API.

**Not built yet (Phase 2/3 of the plan):** the actual AI conversation logic, Telegram/WhatsApp connection, real customer-facing chat. The "Your AI" tab saves a personality — but no AI is using it yet. That's next.

## Storing this properly
Recommendation: put this in a **private GitHub repo**, not just a folder on your computer. It's free, it's how every real dev team works, and it means neither of us loses work. If you don't have a GitHub account yet, make one — then:
```
git init
git add .
git commit -m "Initial project skeleton"
git remote add origin <your-repo-url>
git push -u origin main
```
