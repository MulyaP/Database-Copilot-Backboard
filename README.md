# Database Copilot

An AI-powered assistant that lets developers connect their database and chat with it in plain English. The AI writes SQL, explains queries, and remembers context across sessions using Backboard.io's memory API.

## Tech Stack

- **Frontend:** Next.js (App Router) + Tailwind CSS
- **Backend:** FastAPI (Python)
- **Auth:** Supabase Auth (email/password)
- **Memory & LLM:** Backboard.io API
- **App Database:** Supabase (Postgres)

---

## Setup

### 1. Supabase

1. Create a Supabase project at [supabase.com](https://supabase.com)
2. Run the following SQL in the Supabase SQL editor:

```sql
create table connections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  connection_string text not null,
  db_type text not null,
  backboard_assistant_id text not null,
  backboard_thread_id text not null,
  created_at timestamp with time zone default now(),
  unique(user_id)
);

alter table connections enable row level security;

create policy "Users can manage their own connection"
on connections for all
using (auth.uid() = user_id);
```

3. From **Project Settings → API**, copy:
   - **Project URL** → used for both frontend and backend env vars
   - **anon/public key** → frontend `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - **service_role key** → backend `SUPABASE_SERVICE_ROLE_KEY`

### 2. Backboard

1. Create an account at [app.backboard.io](https://app.backboard.io)
2. Go to **Settings → API Keys** and create a new API key
3. Copy the key → backend `BACKBOARD_API_KEY`

### 3. Configure Environment Variables

**`backend/.env`**
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
BACKBOARD_API_KEY=your_backboard_api_key
```

**`frontend/.env.local`**
```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Running the App

### Backend

```bash
cd backend
bash setup.sh
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

> On Windows, activate the virtualenv with: `venv\Scripts\activate`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at [http://localhost:3000](http://localhost:3000).

---

## Usage

1. Open [http://localhost:3000](http://localhost:3000) — you'll be redirected to `/login`
2. Sign up with your email and password
3. On the onboarding screen, paste your database connection string (e.g. `postgresql://user:password@host:5432/dbname`)
4. Click **Connect** — the app reads your schema and initializes the AI assistant
5. You're redirected to the chat interface
6. Ask questions in plain English, e.g.:
   - "Show me all users who signed up this week"
   - "What tables do I have?"
   - "Find the top 10 orders by total amount"
7. When the AI returns SQL, click **Run Query** to execute it and see results inline

---

## Project Structure

```
/
├── backend/
│   ├── main.py                # FastAPI entry point
│   ├── auth.py                # JWT verification via Supabase
│   ├── models.py              # Pydantic request/response models
│   ├── supabase_client.py     # Supabase server client
│   ├── routers/
│   │   ├── onboarding.py      # POST /onboarding/connect
│   │   ├── chat.py            # POST /chat/message
│   │   └── query.py           # POST /query/run
│   ├── services/
│   │   ├── backboard.py       # Backboard API integration
│   │   ├── schema.py          # DB schema introspection
│   │   └── db.py              # User DB query execution
│   ├── requirements.txt
│   └── setup.sh
│
└── frontend/
    ├── app/
    │   ├── page.tsx           # Root redirect logic
    │   ├── login/page.tsx     # Auth page
    │   ├── onboarding/page.tsx
    │   └── chat/page.tsx      # Main chat UI
    ├── components/
    │   ├── ChatWindow.tsx
    │   ├── MessageBubble.tsx
    │   ├── SqlBlock.tsx
    │   └── ResultsTable.tsx
    └── lib/
        └── supabaseClient.ts
```
