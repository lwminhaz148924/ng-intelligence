
import os
import re
import sqlite3
import hashlib
import secrets
import json
import time
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from jose import jwt, JWTError
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

DATA = Path(os.getenv("DATA_DIR", BASE / "data"))
DATA.mkdir(parents=True, exist_ok=True)

WORKSPACE = Path(os.getenv("WORKSPACE_DIR", BASE / "workspace"))
WORKSPACE.mkdir(parents=True, exist_ok=True)

DB = DATA / "ng_intelligence.db"
MODEL_DEFAULT = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
REMOTE_COMMANDS = os.getenv("REMOTE_COMMANDS_ENABLED", "false").lower() == "true"

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
limiter = Limiter(key_func=get_remote_address)


def encryption():
    raw = os.getenv("API_KEY_ENCRYPTION_KEY", "").strip()

    if not raw:
        raw = base64.urlsafe_b64encode(
            hashlib.sha256(JWT_SECRET.encode()).digest()
        )
    else:
        raw = raw.encode()

    return Fernet(raw)


FERNET = encryption()

app = FastAPI(title="NG INTELLIGENCE", version="2.0.0")

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: HTTPException(429, "Too many requests.")
)

app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        x.strip()
        for x in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173"
        ).split(",")
        if x.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def now():
    return datetime.utcnow().isoformat()


SYSTEM_PROMPT = """You are NG INTELLIGENCE, an expert AI coding assistant. You are created or developed by Lw Minhaz
Always communicate in clear, professional English unless the user explicitly requests another language.
Understand Bengali and English.

Capabilities:
1. Build complete software projects.
2. Create Python, Flask, Telegram bot and web projects.
3. Analyze errors and debug source code.
4. Generate corrected complete files.
5. Explain code and suggest improvements.
6. Work with the user's existing workspace.

When creating or modifying files, return each complete file using:
<FILE path="relative/path.ext">
complete source code
</FILE>

Only use relative workspace file paths.
Never claim files were saved by yourself.
Never omit important existing functionality when fixing code.
Do not expose API keys or secrets.
Do not generate malware, credential theft, unauthorized access tools or destructive code.
"""


def init():
    c = conn()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS chats(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS api_keys(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL,
        key_hash TEXT NOT NULL,
        key_cipher TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings(
        name TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event TEXT NOT NULL,
        status TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS usage(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        model TEXT,
        input_chars INTEGER DEFAULT 0,
        output_chars INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    if ADMIN_EMAIL and ADMIN_PASSWORD:
        u = c.execute(
            "SELECT id FROM users WHERE email=?",
            (ADMIN_EMAIL.lower().strip(),)
        ).fetchone()

        if not u:
            c.execute(
                "INSERT INTO users(email,password_hash,role,created_at) VALUES(?,?,?,?)",
                (
                    ADMIN_EMAIL.lower().strip(),
                    pwd.hash(ADMIN_PASSWORD),
                    "admin",
                    now()
                )
            )

    if not c.execute(
        "SELECT 1 FROM settings WHERE name='system_prompt'"
    ).fetchone():
        c.execute(
            "INSERT INTO settings(name,value) VALUES(?,?)",
            ("system_prompt", SYSTEM_PROMPT)
        )

    c.commit()
    c.close()


init()


class Auth(BaseModel):
    email: EmailStr
    password: str


class ChatReq(BaseModel):
    message: str
    chat_id: Optional[int] = None


class KeyReq(BaseModel):
    label: str
    key: str


class SettingReq(BaseModel):
    name: str
    value: str


class ProjectReq(BaseModel):
    name: str


class FileReq(BaseModel):
    path: str
    content: Optional[str] = None


def token(u):
    return jwt.encode(
        {
            "sub": str(u["id"]),
            "role": u["role"],
            "exp": datetime.utcnow() + timedelta(days=7)
        },
        JWT_SECRET,
        algorithm="HS256"
    )


def current(authorization: str = Header("")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")

    try:
        p = jwt.decode(
            authorization[7:],
            JWT_SECRET,
            algorithms=["HS256"]
        )

        c = conn()
        u = c.execute(
            "SELECT * FROM users WHERE id=? AND active=1",
            (int(p["sub"]),)
        ).fetchone()
        c.close()

        if not u:
            raise HTTPException(401, "Account not found or disabled")

        return u

    except (JWTError, ValueError):
        raise HTTPException(401, "Invalid or expired session")


def admin(u=Depends(current)):
    if u["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return u


def log(user_id, event, status, details=""):
    c = conn()
    c.execute(
        "INSERT INTO logs(user_id,event,status,details,created_at) VALUES(?,?,?,?,?)",
        (user_id, event, status, details[:2000], now())
    )
    c.commit()
    c.close()


def safe_path(rel):
    rel = rel.strip().replace("\\", "/")

    if (
        not rel
        or rel.startswith("/")
        or rel.startswith("../")
        or "/../" in rel
        or ":" in rel
    ):
        raise HTTPException(400, "Unsafe workspace path.")

    target = (WORKSPACE / rel).resolve()
    root = WORKSPACE.resolve()

    if root != target and root not in target.parents:
        raise HTTPException(400, "Path outside workspace.")

    return target


def get_setting(name, fallback=""):
    c = conn()
    r = c.execute(
        "SELECT value FROM settings WHERE name=?",
        (name,)
    ).fetchone()
    c.close()

    return r["value"] if r else fallback


def keys():
    env = os.getenv("GEMINI_API_KEY", "").strip()
    out = []

    if env:
        out.append(("ENV", env))

    c = conn()

    for r in c.execute(
        "SELECT id,label,key_cipher FROM api_keys WHERE active=1 ORDER BY id"
    ):
        try:
            out.append(
                (
                    r["label"],
                    FERNET.decrypt(r["key_cipher"].encode()).decode()
                )
            )
        except Exception:
            pass

    c.close()
    return out


def gemini(prompt):
    active = keys()

    if not active:
        raise HTTPException(503, "Gemini API key is not configured.")

    model = get_setting("model", MODEL_DEFAULT)
    last = None

    for label, key in active:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/"
                f"v1beta/models/{model}:generateContent"
            )

            payload = {
                "systemInstruction": {
                    "parts": [
                        {"text": get_setting("system_prompt", SYSTEM_PROMPT)}
                    ]
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 8192
                }
            }

            r = requests.post(
                url,
                headers={
                    "x-goog-api-key": key,
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=90
            )

            if r.ok:
                d = r.json()
                parts = (
                    d.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )

                ans = "\n".join(
                    x.get("text", "")
                    for x in parts
                    if x.get("text")
                ).strip()

                if ans:
                    return ans, model, label

            last = f"{label}: HTTP {r.status_code}"

        except Exception as e:
            last = f"{label}: {e}"

    raise HTTPException(
        502,
        f"All configured Gemini keys failed. {last or ''}".strip()
    )


def extract_files(answer):
    return [
        {"path": p, "content": content.strip()}
        for p, content in re.findall(
            r'<FILE\s+path=["\']([^"\']+)["\']\s*>(.*?)</FILE>',
            answer,
            re.I | re.S
        )
    ]


@app.get("/api/health")
def health():
    return {
        "online": True,
        "provider": "GEMINI",
        "model": get_setting("model", MODEL_DEFAULT),
        "api_configured": bool(keys())
    }


@app.post("/api/auth/register")
@limiter.limit("5/minute")
def register(request: Request, a: Auth):
    if len(a.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")

    c = conn()

    try:
        cur = c.execute(
            "INSERT INTO users(email,password_hash,role,created_at) VALUES(?,?,?,?)",
            (a.email.lower(), pwd.hash(a.password), "user", now())
        )
        c.commit()

        u = c.execute(
            "SELECT * FROM users WHERE id=?",
            (cur.lastrowid,)
        ).fetchone()

        return {
            "token": token(u),
            "user": {
                "id": u["id"],
                "email": u["email"],
                "role": u["role"]
            }
        }

    except sqlite3.IntegrityError:
        raise HTTPException(409, "Account already exists.")

    finally:
        c.close()


@app.post("/api/auth/login")
@limiter.limit("10/minute")
def login(request: Request, a: Auth):
    c = conn()
    u = c.execute(
        "SELECT * FROM users WHERE email=?",
        (a.email.lower(),)
    ).fetchone()
    c.close()

    if not u or not pwd.verify(a.password, u["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")

    return {
        "token": token(u),
        "user": {
            "id": u["id"],
            "email": u["email"],
            "role": u["role"]
        }
    }


@app.get("/api/me")
def me(u=Depends(current)):
    return {
        "id": u["id"],
        "email": u["email"],
        "role": u["role"]
    }


@app.get("/api/chats")
def list_chats(u=Depends(current)):
    c = conn()
    rows = c.execute(
        "SELECT id,title,created_at,updated_at FROM chats WHERE user_id=? ORDER BY updated_at DESC",
        (u["id"],)
    ).fetchall()
    c.close()

    return [dict(r) for r in rows]


@app.get("/api/chats/{chat_id}")
def history(chat_id: int, u=Depends(current)):
    c = conn()
    ok = c.execute(
        "SELECT id FROM chats WHERE id=? AND user_id=?",
        (chat_id, u["id"])
    ).fetchone()

    if not ok:
        c.close()
        raise HTTPException(404, "Chat not found.")

    rows = c.execute(
        "SELECT role,content,created_at FROM messages WHERE chat_id=? ORDER BY id",
        (chat_id,)
    ).fetchall()
    c.close()

    return [dict(r) for r in rows]


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: int, u=Depends(current)):
    c = conn()
    ok = c.execute(
        "SELECT id FROM chats WHERE id=? AND user_id=?",
        (chat_id, u["id"])
    ).fetchone()

    if not ok:
        c.close()
        raise HTTPException(404, "Chat not found.")

    c.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
    c.execute("DELETE FROM chats WHERE id=?", (chat_id,))
    c.commit()
    c.close()

    return {"ok": True}


@app.post("/api/chat")
@limiter.limit("30/minute")
def chat(request: Request, req: ChatReq, u=Depends(current)):
    text = req.message.strip()

    if not text:
        raise HTTPException(400, "Message is empty.")

    c = conn()
    cid = req.chat_id

    if cid:
        ok = c.execute(
            "SELECT id FROM chats WHERE id=? AND user_id=?",
            (cid, u["id"])
        ).fetchone()

        if not ok:
            c.close()
            raise HTTPException(404, "Chat not found.")

    else:
        # FIXED: 4 columns require 4 placeholders.
        cur = c.execute(
            "INSERT INTO chats(user_id,title,created_at,updated_at) VALUES(?,?,?,?)",
            (u["id"], text[:60], now(), now())
        )
        cid = cur.lastrowid

    c.execute(
        "INSERT INTO messages(chat_id,role,content,created_at) VALUES(?,?,?,?)",
        (cid, "user", text, now())
    )

    rows = c.execute(
        "SELECT role,content FROM messages WHERE chat_id=? ORDER BY id",
        (cid,)
    ).fetchall()

    c.commit()
    c.close()

    context = "\n\n".join(
        f"{r['role'].upper()}: {r['content']}"
        for r in rows
    )

    try:
        answer, model, keylabel = gemini(
            "CONVERSATION:\n" + context +
            "\n\nCURRENT USER REQUEST:\n" + text
        )

    except HTTPException as e:
        log(u["id"], "chat", "error", str(e))
        raise

    c = conn()

    c.execute(
        "INSERT INTO messages(chat_id,role,content,created_at) VALUES(?,?,?,?)",
        (cid, "assistant", answer, now())
    )

    c.execute(
        "UPDATE chats SET updated_at=? WHERE id=?",
        (now(), cid)
    )

    c.execute(
        "INSERT INTO usage(user_id,model,input_chars,output_chars,created_at) VALUES(?,?,?,?,?)",
        (u["id"], model, len(text), len(answer), now())
    )

    c.commit()
    c.close()

    log(
        u["id"],
        "chat",
        "success",
        f"model={model},key={keylabel}"
    )

    return {
        "chat_id": cid,
        "answer": answer,
        "files": extract_files(answer),
        "model": model
    }


@app.get("/api/workspace/files")
def files(u=Depends(current)):
    out = []

    for p in WORKSPACE.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            out.append({
                "path": str(p.relative_to(WORKSPACE)).replace("\\", "/"),
                "size": p.stat().st_size
            })

    return sorted(out, key=lambda x: x["path"])


@app.get("/api/workspace/file")
def read_file(path: str, u=Depends(current)):
    p = safe_path(path)

    if not p.is_file():
        raise HTTPException(404, "File not found.")

    return {
        "path": path,
        "content": p.read_text(encoding="utf-8", errors="replace")
    }


@app.post("/api/workspace/file")
def write_file(req: FileReq, u=Depends(current)):
    if req.content is None:
        raise HTTPException(400, "Content is required.")

    p = safe_path(req.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(req.content, encoding="utf-8")

    return {"ok": True, "path": req.path}


@app.post("/api/projects")
def project(req: ProjectReq, u=Depends(current)):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", req.name):
        raise HTTPException(400, "Invalid project name.")

    p = WORKSPACE / req.name

    if p.exists():
        raise HTTPException(409, "Project already exists.")

    p.mkdir(parents=True)

    return {"ok": True, "name": req.name}


@app.post("/api/auto-fix")
def auto_fix(req: FileReq, u=Depends(current)):
    if not req.path or not req.content:
        raise HTTPException(400, "File path and source are required.")

    return {
        "message": "Use /api/chat with the full error and source context for the AI fix workflow."
    }


@app.get("/api/admin/stats")
def admin_stats(u=Depends(admin)):
    c = conn()

    users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    chats = c.execute("SELECT COUNT(*) n FROM chats").fetchone()["n"]
    msgs = c.execute("SELECT COUNT(*) n FROM messages").fetchone()["n"]
    usage_total = c.execute(
        "SELECT COALESCE(SUM(input_chars+output_chars),0) n FROM usage"
    ).fetchone()["n"]
    logs_total = c.execute("SELECT COUNT(*) n FROM logs").fetchone()["n"]

    c.close()

    return {
        "users": users,
        "chats": chats,
        "messages": msgs,
        "characters": usage_total,
        "logs": logs_total
    }


@app.get("/api/admin/keys")
def admin_keys(u=Depends(admin)):
    c = conn()
    rows = c.execute(
        "SELECT id,label,active,created_at FROM api_keys ORDER BY id DESC"
    ).fetchall()
    c.close()

    return [dict(r) for r in rows]


@app.post("/api/admin/keys")
def add_key(req: KeyReq, u=Depends(admin)):
    if not req.key.strip():
        raise HTTPException(400, "API key required.")

    c = conn()
    c.execute(
        "INSERT INTO api_keys(label,key_hash,key_cipher,active,created_at) VALUES(?,?,?,?,?)",
        (
            req.label,
            hashlib.sha256(req.key.encode()).hexdigest(),
            FERNET.encrypt(req.key.strip().encode()).decode(),
            1,
            now()
        )
    )
    c.commit()
    c.close()

    return {"ok": True}


@app.patch("/api/admin/keys/{key_id}")
def toggle_key(key_id: int, u=Depends(admin)):
    c = conn()
    r = c.execute(
        "SELECT active FROM api_keys WHERE id=?",
        (key_id,)
    ).fetchone()

    if not r:
        c.close()
        raise HTTPException(404, "Key not found.")

    c.execute(
        "UPDATE api_keys SET active=? WHERE id=?",
        (0 if r["active"] else 1, key_id)
    )

    c.commit()
    c.close()

    return {"ok": True}


@app.delete("/api/admin/keys/{key_id}")
def remove_key(key_id: int, u=Depends(admin)):
    c = conn()
    c.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
    c.commit()
    c.close()

    return {"ok": True}


@app.get("/api/admin/settings")
def settings(u=Depends(admin)):
    return {
        "model": get_setting("model", MODEL_DEFAULT),
        "system_prompt": get_setting("system_prompt", SYSTEM_PROMPT)
    }


@app.put("/api/admin/settings")
def update_setting(req: SettingReq, u=Depends(admin)):
    if req.name not in {"model", "system_prompt"}:
        raise HTTPException(400, "Unsupported setting.")

    c = conn()
    c.execute(
        "INSERT INTO settings(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
        (req.name, req.value)
    )
    c.commit()
    c.close()

    return {"ok": True}


@app.get("/api/admin/logs")
def logs(u=Depends(admin)):
    c = conn()
    rows = c.execute(
        "SELECT id,user_id,event,status,details,created_at FROM logs ORDER BY id DESC LIMIT 200"
    ).fetchall()
    c.close()

    return [dict(r) for r in rows]


@app.get("/api/admin/users")
def users(u=Depends(admin)):
    c = conn()
    rows = c.execute(
        "SELECT id,email,role,active,created_at FROM users ORDER BY id DESC"
    ).fetchall()
    c.close()

    return [dict(r) for r in rows]


@app.patch("/api/admin/users/{user_id}/toggle")
def toggle_user(user_id: int, u=Depends(admin)):
    c = conn()
    r = c.execute(
        "SELECT active FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not r:
        c.close()
        raise HTTPException(404, "User not found.")

    c.execute(
        "UPDATE users SET active=? WHERE id=?",
        (0 if r["active"] else 1, user_id)
    )

    c.commit()
    c.close()

    return {"ok": True}


@app.get("/api/admin/usage")
def usage(u=Depends(admin)):
    c = conn()
    rows = c.execute("""
        SELECT model,
               COUNT(*) requests,
               SUM(input_chars) input_chars,
               SUM(output_chars) output_chars
        FROM usage
        GROUP BY model
        ORDER BY requests DESC
    """).fetchall()
    c.close()

    return [dict(r) for r in rows]


@app.post("/api/admin/reset-password/{user_id}")
def reset_password(user_id: int, u=Depends(admin)):
    new = secrets.token_urlsafe(10)

    c = conn()
    r = c.execute(
        "SELECT id FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not r:
        c.close()
        raise HTTPException(404, "User not found.")

    c.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (pwd.hash(new), user_id)
    )

    c.commit()
    c.close()

    return {"temporary_password": new}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
