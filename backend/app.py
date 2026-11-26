
import os
import re
import sqlite3
import hashlib
import secrets
import base64
import smtplib

from email.message import EmailMessage
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from jose import jwt, JWTError
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


# =========================================================
# CONFIGURATION
# =========================================================

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

app = FastAPI(title="NG INTELLIGENCE", version="2.2.0")

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."}
    )


app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        x.strip()
        for x in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173"
        ).split(",")
        if x.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# =========================================================
# DATABASE
# =========================================================

def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def now():
    return datetime.utcnow().isoformat()


SYSTEM_PROMPT = """You are NG INTELLIGENCE, an expert AI coding assistant.
You are created or developed by Lw Minhaz.

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

    CREATE TABLE IF NOT EXISTS verification_codes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        code_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    columns = [
        row["name"]
        for row in c.execute("PRAGMA table_info(users)").fetchall()
    ]

    if "is_verified" not in columns:
        c.execute(
            "ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 1"
        )

    if ADMIN_EMAIL and ADMIN_PASSWORD:
        admin_email = ADMIN_EMAIL.lower().strip()

        existing_admin = c.execute(
            "SELECT id FROM users WHERE email=?",
            (admin_email,)
        ).fetchone()

        if not existing_admin:
            c.execute(
                """
                INSERT INTO users(
                    email, password_hash, role, created_at, is_verified
                )
                VALUES(?,?,?,?,1)
                """,
                (
                    admin_email,
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


# =========================================================
# REQUEST MODELS
# =========================================================

class Auth(BaseModel):
    email: EmailStr
    password: str


class EmailOnly(BaseModel):
    email: EmailStr


class VerifyReq(BaseModel):
    email: EmailStr
    code: str


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


# =========================================================
# AUTHENTICATION
# =========================================================

def token(u):
    return jwt.encode(
        {
            "sub": str(u["id"]),
            "role": u["role"],
            "exp": datetime.utcnow() + timedelta(days=30)
        },
        JWT_SECRET,
        algorithm="HS256"
    )


def current(authorization: str = Header("")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")

    try:
        payload = jwt.decode(
            authorization[7:],
            JWT_SECRET,
            algorithms=["HS256"]
        )

        c = conn()
        u = c.execute(
            "SELECT * FROM users WHERE id=? AND active=1",
            (int(payload["sub"]),)
        ).fetchone()
        c.close()

        if not u:
            raise HTTPException(401, "Account not found or disabled")

        return u

    except (JWTError, ValueError, TypeError):
        raise HTTPException(401, "Invalid or expired session")


def admin(u=Depends(current)):
    if u["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return u


def log(user_id, event, status, details=""):
    c = conn()
    c.execute(
        """
        INSERT INTO logs(user_id,event,status,details,created_at)
        VALUES(?,?,?,?,?)
        """,
        (user_id, event, status, str(details)[:2000], now())
    )
    c.commit()
    c.close()


# =========================================================
# EMAIL VERIFICATION
# =========================================================

def send_verification_email(to_email, code):
    smtp_email = os.getenv("SMTP_EMAIL", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()

    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        raise HTTPException(503, "Invalid SMTP port configuration.")

    if not smtp_email or not smtp_password:
        raise HTTPException(
            503,
            "Email service is not configured. Please contact support."
        )

    message = EmailMessage()
    message["Subject"] = "NG INTELLIGENCE - Email Verification"
    message["From"] = smtp_email
    message["To"] = to_email

    message.set_content(
        f"""Welcome to NG INTELLIGENCE!

Your email verification code is:

{code}

This code expires in 10 minutes.

If you did not create this account, you can ignore this email.

Created by Lw Minhaz
"""
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(message)

    except Exception as e:
        print(
            f"[SMTP ERROR] {type(e).__name__}: {e}",
            flush=True
        )
        raise HTTPException(
            503,
            "Unable to send verification email. Please try again later."
        )


def create_verification_code(email):
    code = f"{secrets.randbelow(1000000):06d}"
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires = (
        datetime.utcnow() + timedelta(minutes=10)
    ).isoformat()

    c = conn()
    c.execute(
        """
        INSERT INTO verification_codes(
            email,code_hash,expires_at,attempts,created_at
        )
        VALUES(?,?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET
            code_hash=excluded.code_hash,
            expires_at=excluded.expires_at,
            attempts=0,
            created_at=excluded.created_at
        """,
        (email, code_hash, expires, 0, now())
    )
    c.commit()
    c.close()

    return code


# =========================================================
# WORKSPACE HELPERS
# =========================================================

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


# =========================================================
# GEMINI API
# =========================================================

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
                "https://generativelanguage.googleapis.com/"
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
                data = r.json()
                parts = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )

                answer = "\n".join(
                    x.get("text", "")
                    for x in parts
                    if x.get("text")
                ).strip()

                if answer:
                    return answer, model, label

            last = f"{label}: HTTP {r.status_code}"

        except Exception as e:
            last = f"{label}: {type(e).__name__}"

    raise HTTPException(
        502,
        f"All configured Gemini keys failed. {last or ''}".strip()
    )


def extract_files(answer):
    return [
        {"path": path, "content": content.strip()}
        for path, content in re.findall(
            r'<FILE\s+path=["\']([^"\']+)["\']\s*>(.*?)</FILE>',
            answer,
            re.I | re.S
        )
    ]


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():
    return {
        "online": True,
        "provider": "GEMINI",
        "model": get_setting("model", MODEL_DEFAULT),
        "api_configured": bool(keys())
    }


# =========================================================
# REGISTER
# =========================================================

@app.post("/api/auth/register")
@limiter.limit("5/minute")
def register(request: Request, a: Auth):
    email = a.email.lower().strip()

    if len(a.password) < 8:
        raise HTTPException(
            400,
            "Password must be at least 8 characters."
        )

    c = conn()

    try:
        existing = c.execute(
            "SELECT id FROM users WHERE email=?",
            (email,)
        ).fetchone()

        if existing:
            raise HTTPException(409, "Account already exists.")

        c.execute(
            """
            INSERT INTO users(
                email,password_hash,role,created_at,is_verified
            )
            VALUES(?,?,?,?,0)
            """,
            (
                email,
                pwd.hash(a.password),
                "user",
                now()
            )
        )

        c.commit()

    except sqlite3.IntegrityError:
        c.rollback()
        raise HTTPException(409, "Account already exists.")

    finally:
        c.close()

    try:
        code = create_verification_code(email)
        send_verification_email(email, code)

    except HTTPException:
        cleanup = conn()
        cleanup.execute(
            "DELETE FROM verification_codes WHERE email=?",
            (email,)
        )
        cleanup.execute(
            "DELETE FROM users WHERE email=? AND is_verified=0",
            (email,)
        )
        cleanup.commit()
        cleanup.close()
        raise

    except Exception:
        cleanup = conn()
        cleanup.execute(
            "DELETE FROM verification_codes WHERE email=?",
            (email,)
        )
        cleanup.execute(
            "DELETE FROM users WHERE email=? AND is_verified=0",
            (email,)
        )
        cleanup.commit()
        cleanup.close()
        raise HTTPException(503, "Registration could not be completed.")

    return {
        "verification_required": True,
        "email": email,
        "message": "Verification code sent to your email."
    }


# =========================================================
# VERIFY EMAIL
# =========================================================

@app.post("/api/auth/verify")
@limiter.limit("10/minute")
def verify_email(request: Request, req: VerifyReq):
    email = req.email.lower().strip()
    code = req.code.strip()

    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(
            400,
            "Enter a valid 6-digit verification code."
        )

    c = conn()

    try:
        user = c.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        ).fetchone()

        if not user:
            raise HTTPException(404, "Account not found.")

        if user["is_verified"]:
            raise HTTPException(400, "Email is already verified.")

        record = c.execute(
            "SELECT * FROM verification_codes WHERE email=?",
            (email,)
        ).fetchone()

        if not record:
            raise HTTPException(
                400,
                "Verification code not found. Request a new code."
            )

        if record["attempts"] >= 5:
            raise HTTPException(
                429,
                "Too many incorrect attempts. Request a new code."
            )

        if datetime.utcnow() > datetime.fromisoformat(record["expires_at"]):
            raise HTTPException(
                400,
                "Verification code expired. Request a new code."
            )

        supplied_hash = hashlib.sha256(code.encode()).hexdigest()

        if not secrets.compare_digest(
            supplied_hash,
            record["code_hash"]
        ):
            c.execute(
                """
                UPDATE verification_codes
                SET attempts=attempts+1
                WHERE email=?
                """,
                (email,)
            )
            c.commit()

            raise HTTPException(400, "Incorrect verification code.")

        c.execute(
            "UPDATE users SET is_verified=1 WHERE email=?",
            (email,)
        )

        c.execute(
            "DELETE FROM verification_codes WHERE email=?",
            (email,)
        )

        c.commit()

        verified_user = c.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        ).fetchone()

    finally:
        c.close()

    return {
        "token": token(verified_user),
        "user": {
            "id": verified_user["id"],
            "email": verified_user["email"],
            "role": verified_user["role"]
        },
        "message": "Email verified successfully."
    }


# =========================================================
# RESEND VERIFICATION
# =========================================================

@app.post("/api/auth/resend-verification")
@limiter.limit("3/minute")
def resend_verification(request: Request, req: EmailOnly):
    email = req.email.lower().strip()

    c = conn()
    user = c.execute(
        "SELECT * FROM users WHERE email=?",
        (email,)
    ).fetchone()
    c.close()

    if not user:
        raise HTTPException(404, "Account not found.")

    if user["is_verified"]:
        raise HTTPException(400, "Email is already verified.")

    code = f"{secrets.randbelow(1000000):06d}"

    send_verification_email(email, code)

    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires = (
        datetime.utcnow() + timedelta(minutes=10)
    ).isoformat()

    c = conn()
    c.execute(
        """
        INSERT INTO verification_codes(
            email,code_hash,expires_at,attempts,created_at
        )
        VALUES(?,?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET
            code_hash=excluded.code_hash,
            expires_at=excluded.expires_at,
            attempts=0,
            created_at=excluded.created_at
        """,
        (email, code_hash, expires, 0, now())
    )
    c.commit()
    c.close()

    return {
        "ok": True,
        "message": "A new verification code has been sent."
    }


# =========================================================
# LOGIN
# =========================================================

@app.post("/api/auth/login")
@limiter.limit("10/minute")
def login(request: Request, a: Auth):
    c = conn()

    u = c.execute(
        "SELECT * FROM users WHERE email=?",
        (a.email.lower().strip(),)
    ).fetchone()

    c.close()

    if not u or not pwd.verify(a.password, u["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")

    if not u["active"]:
        raise HTTPException(403, "Account is disabled.")

    if not u["is_verified"]:
        raise HTTPException(
            403,
            "Email verification required. Please verify your email first."
        )

    return {
        "token": token(u),
        "user": {
            "id": u["id"],
            "email": u["email"],
            "role": u["role"]
        }
    }


# =========================================================
# CURRENT USER
# =========================================================

@app.get("/api/me")
def me(u=Depends(current)):
    return {
        "id": u["id"],
        "email": u["email"],
        "role": u["role"]
    }


# =========================================================
# CHAT HISTORY
# =========================================================

@app.get("/api/chats")
def list_chats(u=Depends(current)):
    c = conn()

    rows = c.execute(
        """
        SELECT id,title,created_at,updated_at
        FROM chats
        WHERE user_id=?
        ORDER BY updated_at DESC
        """,
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
        """
        SELECT role,content,created_at
        FROM messages
        WHERE chat_id=?
        ORDER BY id
        """,
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


# =========================================================
# AI CHAT
# =========================================================

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
        cur = c.execute(
            """
            INSERT INTO chats(user_id,title,created_at,updated_at)
            VALUES(?,?,?,?)
            """,
            (u["id"], text[:60], now(), now())
        )
        cid = cur.lastrowid

    c.execute(
        """
        INSERT INTO messages(chat_id,role,content,created_at)
        VALUES(?,?,?,?)
        """,
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
        log(u["id"], "chat", "error", str(e.detail))
        raise

    c = conn()

    c.execute(
        """
        INSERT INTO messages(chat_id,role,content,created_at)
        VALUES(?,?,?,?)
        """,
        (cid, "assistant", answer, now())
    )

    c.execute(
        "UPDATE chats SET updated_at=? WHERE id=?",
        (now(), cid)
    )

    c.execute(
        """
        INSERT INTO usage(
            user_id,model,input_chars,output_chars,created_at
        )
        VALUES(?,?,?,?,?)
        """,
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


# =========================================================
# WORKSPACE
# =========================================================

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
        "content": p.read_text(
            encoding="utf-8",
            errors="replace"
        )
    }


@app.post("/api/workspace/file")
def write_file(req: FileReq, u=Depends(current)):
    if req.content is None:
        raise HTTPException(400, "Content is required.")

    p = safe_path(req.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(req.content, encoding="utf-8")

    return {"ok": True, "path": req.path}


# =========================================================
# PROJECTS
# =========================================================

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
        raise HTTPException(
            400,
            "File path and source are required."
        )

    return {
        "message": (
            "Use /api/chat with the full error and source context "
            "for the AI fix workflow."
        )
    }


# =========================================================
# ADMIN STATS
# =========================================================

@app.get("/api/admin/stats")
def admin_stats(u=Depends(admin)):
    c = conn()

    users_count = c.execute(
        "SELECT COUNT(*) n FROM users"
    ).fetchone()["n"]

    chats_count = c.execute(
        "SELECT COUNT(*) n FROM chats"
    ).fetchone()["n"]

    messages_count = c.execute(
        "SELECT COUNT(*) n FROM messages"
    ).fetchone()["n"]

    usage_total = c.execute(
        "SELECT COALESCE(SUM(input_chars+output_chars),0) n FROM usage"
    ).fetchone()["n"]

    logs_total = c.execute(
        "SELECT COUNT(*) n FROM logs"
    ).fetchone()["n"]

    c.close()

    return {
        "users": users_count,
        "chats": chats_count,
        "messages": messages_count,
        "characters": usage_total,
        "logs": logs_total
    }


# =========================================================
# ADMIN API KEYS
# =========================================================

@app.get("/api/admin/keys")
def admin_keys(u=Depends(admin)):
    c = conn()

    rows = c.execute(
        """
        SELECT id,label,active,created_at
        FROM api_keys
        ORDER BY id DESC
        """
    ).fetchall()

    c.close()
    return [dict(r) for r in rows]


@app.post("/api/admin/keys")
def add_key(req: KeyReq, u=Depends(admin)):
    if not req.key.strip():
        raise HTTPException(400, "API key required.")

    c = conn()

    c.execute(
        """
        INSERT INTO api_keys(label,key_hash,key_cipher,active,created_at)
        VALUES(?,?,?,?,?)
        """,
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

    c.execute(
        "DELETE FROM api_keys WHERE id=?",
        (key_id,)
    )

    c.commit()
    c.close()

    return {"ok": True}


# =========================================================
# ADMIN SETTINGS
# =========================================================

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
        """
        INSERT INTO settings(name,value)
        VALUES(?,?)
        ON CONFLICT(name) DO UPDATE SET value=excluded.value
        """,
        (req.name, req.value)
    )

    c.commit()
    c.close()

    return {"ok": True}


# =========================================================
# ADMIN LOGS
# =========================================================

@app.get("/api/admin/logs")
def logs(u=Depends(admin)):
    c = conn()

    rows = c.execute(
        """
        SELECT id,user_id,event,status,details,created_at
        FROM logs
        ORDER BY id DESC
        LIMIT 200
        """
    ).fetchall()

    c.close()
    return [dict(r) for r in rows]


# =========================================================
# ADMIN USERS
# =========================================================

@app.get("/api/admin/users")
def users(u=Depends(admin)):
    c = conn()

    rows = c.execute(
        """
        SELECT id,email,role,active,created_at,is_verified
        FROM users
        ORDER BY id DESC
        """
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


@app.post("/api/admin/reset-password/{user_id}")
def reset_password(user_id: int, u=Depends(admin)):
    new_password = secrets.token_urlsafe(10)

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
        (pwd.hash(new_password), user_id)
    )

    c.commit()
    c.close()

    return {"temporary_password": new_password}


# =========================================================
# ADMIN USAGE
# =========================================================

@app.get("/api/admin/usage")
def usage(u=Depends(admin)):
    c = conn()

    rows = c.execute("""
        SELECT
            model,
            COUNT(*) requests,
            SUM(input_chars) input_chars,
            SUM(output_chars) output_chars
        FROM usage
        GROUP BY model
        ORDER BY requests DESC
    """).fetchall()

    c.close()
    return [dict(r) for r in rows]


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
