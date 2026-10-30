import re, time, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import llm, metro

BASE = Path(__file__).parent
DB_FILE = BASE / "chat.db"
MAX_LEN = 500        # longest allowed message
HISTORY_LIMIT = 6    # messages remembered per session

app = FastAPI(title="NammaAI")


def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db():
    conn = db()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY, created_at TEXT);
    CREATE TABLE IF NOT EXISTS messages(message_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
        role TEXT, content TEXT, latency_ms INTEGER, tokens_used INTEGER, provider TEXT, model TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS feedback(feedback_id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER,
        rating INTEGER, note TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS test_results(test_id TEXT, run_at TEXT, query TEXT, expected TEXT,
        actual TEXT, correct INTEGER, latency_ms INTEGER);
    """)
    conn.commit()
    conn.close()


init_db()

# Privacy filter: removes phone numbers, emails, USN-like ids and long digit strings
PATTERNS = [
    r"(?<!\d)(?:\+91[\s-]?|0)?[6-9]\d{9}(?!\d)",
    r"[\w.+-]+@[\w-]+\.[\w.]+",
    r"\b\d[A-Za-z]{2}\d{2}[A-Za-z]{2}\d{3}\b",
    r"\b\d{12,16}\b",
]


def scrub(text):
    found = False
    for p in PATTERNS:
        text, n = re.subn(p, "[removed]", text)
        found = found or n > 0
    return text, found


class ChatIn(BaseModel):
    session_id: str
    message: str
    language: str = "auto"
    length: str = "short"


class RouteIn(BaseModel):
    origin: str
    destination: str
    preference: str = "fastest"


class FeedbackIn(BaseModel):
    message_id: int
    rating: int
    note: str = ""


@app.post("/api/chat")
def chat(body: ChatIn):
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "Please type a message first.")
    if len(text) > MAX_LEN:
        raise HTTPException(400, f"That message is too long. Please keep it under {MAX_LEN} characters.")
    text, scrubbed = scrub(text)

    conn = db()
    conn.execute("INSERT OR IGNORE INTO sessions VALUES (?,?)", (body.session_id, now()))
    rows = conn.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY message_id DESC LIMIT ?",
                        (body.session_id, HISTORY_LIMIT)).fetchall()
    history = [{"role": "assistant" if r["role"] == "bot" else "user", "content": r["content"]} for r in reversed(rows)]
    history.append({"role": "user", "content": text})
    conn.execute("INSERT INTO messages(session_id,role,content,created_at) VALUES (?,?,?,?)",
                 (body.session_id, "user", text, now()))
    conn.commit()

    start = time.time()
    try:
        reply, cards, tokens, provider, model = llm.ask(history, body.language, body.length)
    except llm.NoProvider:
        conn.close()
        raise HTTPException(503, "No AI key is set up. Add your key to the .env file and restart the server.")
    except Exception:
        conn.close()
        raise HTTPException(503, "The AI service is busy or offline (rate limit or network). Wait a moment and try again, or use the Trip planner, which works without AI.")
    ms = int((time.time() - start) * 1000)

    cur = conn.execute("INSERT INTO messages(session_id,role,content,latency_ms,tokens_used,provider,model,created_at) VALUES (?,?,?,?,?,?,?,?)",
                       (body.session_id, "bot", reply, ms, tokens, provider, model, now()))
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return {"reply": reply, "cards": cards, "latency_ms": ms, "provider": provider, "model": model,
            "message_id": mid, "scrubbed": scrubbed, "tokens_used": tokens}


@app.get("/api/history/{session_id}")
def history(session_id: str):
    conn = db()
    rows = conn.execute("SELECT message_id, role, content, created_at FROM messages WHERE session_id=? ORDER BY message_id",
                        (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/feedback")
def feedback(body: FeedbackIn):
    if body.rating not in (1, -1):
        raise HTTPException(400, "Rating must be 1 or -1.")
    conn = db()
    conn.execute("INSERT INTO feedback(message_id,rating,note,created_at) VALUES (?,?,?,?)",
                 (body.message_id, body.rating, scrub(body.note[:200])[0], now()))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/reset/{session_id}")
def reset(session_id: str):
    conn = db()
    conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/route")
def route(body: RouteIn):
    """Trip planner: no AI involved, so it works even when the AI is rate limited."""
    result = metro.find_route(body.origin, body.destination, body.preference)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.get("/api/info")
def info():
    return {
        "app": "NammaAI", "as_of": metro.DATA["as_of"], "alerts": metro.DATA["alerts"],
        "providers": [{"name": p["name"], "model": p["model"]} for p in llm.providers()],
        "stations": sorted(metro.lines_of),
        "lines": [{"name": n, "color": l["color"], "stations": len(l["stations"])} for n, l in metro.DATA["lines"].items() if l["status"] == "operational"],
    }


@app.get("/api/stats")
def stats():
    """Usage numbers from the database, handy for the demo and the report."""
    conn = db()
    m = conn.execute("SELECT COUNT(*) n, AVG(latency_ms) avg_ms, MAX(latency_ms) max_ms, SUM(tokens_used) tokens FROM messages WHERE role='bot'").fetchone()
    f = conn.execute("SELECT COALESCE(SUM(rating=1),0) up, COALESCE(SUM(rating=-1),0) down FROM feedback").fetchone()
    t = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(correct),0) ok FROM test_results").fetchone()
    conn.close()
    return {"bot_replies": m["n"], "avg_latency_ms": round(m["avg_ms"] or 0), "max_latency_ms": m["max_ms"] or 0,
            "total_tokens": m["tokens"] or 0, "thumbs_up": f["up"], "thumbs_down": f["down"],
            "tests_run": t["n"], "tests_passed": t["ok"]}


# must stay last: serves the frontend
app.mount("/", StaticFiles(directory=BASE / "static", html=True), name="static")
