# Database Copilot

**Live demo:** https://database-copilot-backboard-frontend.vercel.app

An AI-powered assistant that lets developers connect their database and chat with it in plain English. The AI writes and executes SQL using an agentic loop — running SELECT queries automatically and pausing for user approval before any INSERT or UPDATE.

## Tech Stack

- **Frontend:** Next.js (App Router) + Tailwind CSS
- **Backend:** FastAPI (Python)
- **Auth:** Supabase Auth (email/password)
- **LLM:** Groq API (`llama-3.3-70b-versatile`)
- **App Database:** Supabase (Postgres)
- **Supported User DBs:** PostgreSQL, MySQL, SQLite

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

### 2. Groq

1. Create an account at [console.groq.com](https://console.groq.com)
2. Go to **API Keys** and create a new key
3. Copy the key → backend `GROQ_API_KEY`

### 3. Configure Environment Variables

**`backend/.env`**
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
GROQ_API_KEY=your_groq_api_key

# Comma-separated allowed CORS origins
ALLOWED_ORIGINS=http://localhost:3001

# Log level: INFO for production, DEBUG for local development
LOG_LEVEL=INFO
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
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at [http://localhost:3000](http://localhost:3000).

---

## Screenshots

**Schema introspection** — ask the AI to describe your database and it maps out every table, column, and relationship:
![Schema description](demo/Schema_description.png)

**Automatic SELECT queries** — read-only queries run instantly with results shown inline:
![Two select queries](demo/two_select_queries.png)

**Write query approval** — INSERT and UPDATE queries pause and ask for your approval before touching any data:
![Write permission demo](demo/Write_permission_demo.png)

**Mixed operations** — INSERT approved and executed; DELETE blocked by a foreign key constraint:
![Write and delete query demo](demo/Write_delete_query_demo.png)

---

## How It Works

1. Sign up and paste your database connection string on the onboarding screen
2. The backend introspects your schema and caches it in memory
3. Each chat message kicks off an agentic loop powered by Groq:
   - **SELECT** queries run automatically and results are shown inline
   - **INSERT / UPDATE** queries pause and ask for your approval before executing
   - **Destructive or privileged commands** (DROP, DELETE, ALTER, GRANT, etc.) are blocked server-side regardless of what the LLM generates
4. The loop continues until the LLM has a final answer, hits the query limit (8 iterations), or times out (120s)

---

## Usage

1. Open [http://localhost:3000](http://localhost:3000) — you'll be redirected to `/login`
2. Sign up with your email and password
3. On the onboarding screen, paste your database connection string, e.g.:
   - PostgreSQL: `postgresql://user:password@host:5432/dbname`
   - MySQL: `mysql://user:password@host:3306/dbname`
4. Click **Connect** — the app reads your schema and you're redirected to the chat interface
5. Ask questions in plain English, e.g.:
   - "Show me all users who signed up this week"
   - "What tables do I have?"
   - "Find the top 10 orders by total amount"
   - "Insert a new product called Widget with price 9.99"

---

## Project Structure

```
/
├── backend/
│   ├── main.py                # FastAPI entry point, CORS, rate limiter
│   ├── auth.py                # JWT verification via Supabase
│   ├── models.py              # Pydantic request/response models
│   ├── supabase_client.py     # Supabase server client
│   ├── routers/
│   │   ├── onboarding.py      # POST /onboarding/connect
│   │   ├── chat.py            # POST /chat/message, POST /chat/execute
│   │   └── query.py           # POST /query/run
│   ├── services/
│   │   ├── groq_llm.py        # Groq API client + tool definition
│   │   ├── history.py         # In-memory chat history + schema cache
│   │   ├── schema.py          # DB schema introspection
│   │   └── db.py              # User DB query execution
│   └── requirements.txt
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

---

## Limitations

- Chat history is stored **in memory** — it resets on server restart
- No support for DDL or privilege management by design
- Rate limited to 20 messages/minute per IP
