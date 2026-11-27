import os
import re
import psycopg
from psycopg.rows import dict_row
import hashlib
import secrets
import base64

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

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Configure the Supabase PostgreSQL connection string in Render.")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
if DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgresql+psycopg://"):]

DB = DATABASE_URL

MODEL_DEFAULT = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
limiter = Limiter(key_func=get_remote_address)

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


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

app = FastAPI(title="NG INTELLIGENCE", version="3.0.0")
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."}
    )


app.add_middleware(SlowAPIMiddleware)

cors_origins = [
    item.strip()
    for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if item.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# =========================================================
# DATABASE
# =========================================================

class DatabaseConnection:
    """Small compatibility layer for the existing SQL used by this app."""

    def __init__(self):
        self.raw = psycopg.connect(
            DB,
            row_factory=dict_row,
            connect_timeout=15,
            sslmode="require"
        )

    @staticmethod
    def _sql(query):
        # Existing application queries use SQLite-style qmark placeholders.
        # The app's SQL contains no literal question marks in quoted strings.
        return query.replace("?", "%s")

    def execute(self, query, params=None):
        return self.raw.execute(self._sql(query), params or ())

    def executescript(self, script):
        # Schema contains independent CREATE TABLE statements.
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.raw.execute(statement.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY"))

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def conn():
    return DatabaseConnection()


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

    CREATE TABLE IF NOT EXISTS password_reset_codes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        code_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    columns = [
        row["column_name"]
        for row in c.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'users'"""
        ).fetchall()
    ]

    if "is_verified" not in columns:
        c.execute(
            "ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 1"
        )

    if "avatar_data" not in columns:
        c.execute(
            "ALTER TABLE users ADD COLUMN avatar_data TEXT"
        )

    if ADMIN_EMAIL and ADMIN_PASSWORD:
        admin_email = ADMIN_EMAIL.lower()

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


class PasswordResetReq(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class ProfileReq(BaseModel):
    avatar_data: Optional[str] = None


class BrandingReq(BaseModel):
    logo_data: Optional[str] = None


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

def send_auth_email(to_email, code, purpose="verification"):
    script_url = os.getenv("GOOGLE_SCRIPT_URL", "").strip()
    secret_key = os.getenv("GOOGLE_SCRIPT_SECRET", "").strip()

    if not script_url or not secret_key:
        print("[EMAIL API ERROR] Missing GOOGLE_SCRIPT_URL or GOOGLE_SCRIPT_SECRET", flush=True)
        raise HTTPException(
            503,
            "Google Email API is not configured."
        )

    try:
        response = requests.post(
            script_url,
            json={
                "email": to_email,
                "code": str(code),
                "purpose": purpose,
                "secret": secret_key
            },
            timeout=30
        )

        response.raise_for_status()

        try:
            result = response.json()
        except ValueError:
            print("[EMAIL API ERROR] Google API returned non-JSON response", flush=True)
            raise HTTPException(
                503,
                "Invalid response from Google Email API."
            )

        if not isinstance(result, dict) or not result.get("success"):
            error_message = (
                result.get("error", "Unknown error")
                if isinstance(result, dict)
                else "Unexpected API response"
            )
            print("[EMAIL API ERROR]", error_message, flush=True)
            raise HTTPException(
                503,
                "Unable to send verification email. Please try again later."
            )

        print(f"[EMAIL SENT] {purpose} email sent to {to_email}", flush=True)
        return True

    except HTTPException:
        raise

    except requests.RequestException as error:
        print(
            f"[EMAIL API ERROR] {type(error).__name__}: {error}",
            flush=True
        )
        raise HTTPException(
            503,
            "Google Email service is temporarily unavailable."
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


def delete_pending_registration(email):
    c = conn()
    try:
        c.execute(
            "DELETE FROM verification_codes WHERE email=?",
            (email,)
        )
        c.execute(
            "DELETE FROM users WHERE email=? AND is_verified=0",
            (email,)
        )
        c.commit()
    finally:
        c.close()


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
    try:
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
                continue
    finally:
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

            system_prompt = get_setting("system_prompt", SYSTEM_PROMPT)
            system_prompt += """

RESPONSE AND FILE OUTPUT RULES:
- For ordinary questions, answer normally. Never print the literal tags <FILE> or </FILE>.
- When the user asks you to create, build, write, or modify code/project files, return every complete file using exactly <FILE path=\"relative/path.ext\"> followed by the full file content and then </FILE>.
- Put a short explanation outside the file blocks. Do not wrap a FILE block in Markdown code fences.
- Do not omit files needed for the requested working project.
- Never claim that files have been saved to the user's device; the interface will provide downloadable file attachments.
"""

            payload = {
                "systemInstruction": {
                    "parts": [
                        {"text": system_prompt}
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
                    item.get("text", "")
                    for item in parts
                    if item.get("text")
                ).strip()

                if answer:
                    return answer, model, label

            last = f"{label}: HTTP {r.status_code}"

        except Exception as error:
            last = f"{label}: {type(error).__name__}"

    raise HTTPException(
        502,
        f"All configured Gemini keys failed. {last or ''}".strip()
    )


def extract_files(answer):
    files = []
    for path, content in re.findall(
        r'<FILE\s+path=["\']([^"\']+)["\']\s*>(.*?)</FILE>',
        answer,
        re.I | re.S
    ):
        path = path.strip().replace("\\", "/")
        if not path or path.startswith("/") or ".." in path.split("/") or ":" in path:
            continue
        files.append({"path": path, "content": content.strip()})
    return files


# =========================================================
# HEALTH
# =========================================================

@app.get("/")
def root():
    return {"name": "NG INTELLIGENCE", "status": "online", "version": "3.0.0"}


@app.get("/api/health")
def health():
    c = conn()
    try:
        c.execute("SELECT 1").fetchone()
    finally:
        c.close()
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
    email = str(a.email).lower().strip()

    if len(a.password) < 8:
        raise HTTPException(
            400,
            "Password must be at least 8 characters."
        )

    c = conn()

    try:
        existing = c.execute(
            "SELECT id, is_verified FROM users WHERE email=?",
            (email,)
        ).fetchone()

        if existing:
            if not existing["is_verified"]:
                raise HTTPException(
                    409,
                    "An unverified account already exists. Request a new verification code."
                )
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

    except psycopg.IntegrityError:
        c.rollback()
        raise HTTPException(409, "Account already exists.")

    finally:
        c.close()

    try:
        code = create_verification_code(email)
        send_auth_email(email, code, "verification")

    except HTTPException:
        delete_pending_registration(email)
        raise

    except Exception as error:
        print(
            f"[REGISTER ERROR] {type(error).__name__}: {error}",
            flush=True
        )
        delete_pending_registration(email)
        raise HTTPException(
            503,
            "Registration could not be completed."
        )

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
    email = str(req.email).lower().strip()
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
            "role": verified_user["role"],
            "avatar_data": verified_user.get("avatar_data")
        },
        "message": "Email verified successfully."
    }


# =========================================================
# RESEND VERIFICATION
# =========================================================

@app.post("/api/auth/resend-verification")
@limiter.limit("3/minute")
def resend_verification(request: Request, req: EmailOnly):
    email = str(req.email).lower().strip()

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

    # Store the new code before sending it, so the emailed code
    # is the same code that the verification endpoint checks.
    code = create_verification_code(email)

    try:
        send_auth_email(email, code, "verification")
    except HTTPException:
        # Keep the pending account and code record. The user can
        # request another code; the previous code may not have arrived.
        raise

    return {
        "ok": True,
        "verification_required": True,
        "email": email,
        "message": "A new verification code has been sent."
    }


# =========================================================
# FORGOT PASSWORD / RESET PASSWORD
# =========================================================

def create_password_reset_code(email):
    code = f"{secrets.randbelow(1000000):06d}"
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

    c = conn()
    c.execute(
        """
        INSERT INTO password_reset_codes(
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


@app.post("/api/auth/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, req: EmailOnly):
    email = str(req.email).lower().strip()

    c = conn()
    user = c.execute(
        "SELECT id,is_verified,active FROM users WHERE email=?",
        (email,)
    ).fetchone()
    c.close()

    generic_message = (
        "If a verified account exists for this email, "
        "a password reset code has been sent."
    )

    if not user or not user["is_verified"] or not user["active"]:
        return {"ok": True, "message": generic_message}

    code = create_password_reset_code(email)

    try:
        send_auth_email(email, code, "password_reset")
    except HTTPException:
        c = conn()
        c.execute(
            "DELETE FROM password_reset_codes WHERE email=?",
            (email,)
        )
        c.commit()
        c.close()
        raise

    return {"ok": True, "message": generic_message}


@app.post("/api/auth/reset-password")
@limiter.limit("5/minute")
def complete_password_reset(request: Request, req: PasswordResetReq):
    email = str(req.email).lower().strip()
    code = req.code.strip()

    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(400, "Enter a valid 6-digit reset code.")

    if len(req.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters.")

    c = conn()

    try:
        user = c.execute(
            "SELECT id,is_verified,active FROM users WHERE email=?",
            (email,)
        ).fetchone()

        if not user or not user["is_verified"] or not user["active"]:
            raise HTTPException(400, "Invalid or expired reset request.")

        record = c.execute(
            "SELECT * FROM password_reset_codes WHERE email=?",
            (email,)
        ).fetchone()

        if not record:
            raise HTTPException(400, "Reset code not found. Request a new code.")

        if record["attempts"] >= 5:
            raise HTTPException(429, "Too many incorrect attempts. Request a new code.")

        if datetime.utcnow() > datetime.fromisoformat(record["expires_at"]):
            c.execute("DELETE FROM password_reset_codes WHERE email=?", (email,))
            c.commit()
            raise HTTPException(400, "Reset code expired. Request a new code.")

        supplied_hash = hashlib.sha256(code.encode()).hexdigest()

        if not secrets.compare_digest(supplied_hash, record["code_hash"]):
            c.execute(
                "UPDATE password_reset_codes SET attempts=attempts+1 WHERE email=?",
                (email,)
            )
            c.commit()
            raise HTTPException(400, "Incorrect reset code.")

        c.execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (pwd.hash(req.new_password), email)
        )
        c.execute(
            "DELETE FROM password_reset_codes WHERE email=?",
            (email,)
        )
        c.commit()

    finally:
        c.close()

    return {
        "ok": True,
        "message": "Password reset successfully. You can now sign in."
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
        (str(a.email).lower().strip(),)
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
            "role": u["role"],
            "avatar_data": u.get("avatar_data")
        }
    }


# =========================================================
# PROFILE / BRANDING HELPERS
# =========================================================

def validate_image_data(value: Optional[str], label: str):
    if value is None or value == "":
        return value
    if not value.startswith("data:image/"):
        raise HTTPException(400, f"Invalid {label} image format.")
    if len(value) > 2_800_000:
        raise HTTPException(400, f"{label.title()} image is too large. Maximum is 2 MB.")
    return value


# =========================================================
# CURRENT USER
# =========================================================

@app.get("/api/me")
def me(u=Depends(current)):
    return {
        "id": u["id"],
        "email": u["email"],
        "role": u["role"],
        "avatar_data": u.get("avatar_data")
    }


@app.put("/api/profile")
def update_profile(req: ProfileReq, u=Depends(current)):
    avatar = validate_image_data(req.avatar_data, "profile")
    c = conn()
    c.execute("UPDATE users SET avatar_data=? WHERE id=?", (avatar, u["id"]))
    c.commit()
    updated = c.execute("SELECT id,email,role,avatar_data FROM users WHERE id=?", (u["id"],)).fetchone()
    c.close()
    return {"ok": True, "user": dict(updated)}


@app.get("/api/branding")
def branding():
    return {"logo_data": get_setting("site_logo", "")}


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
    return [dict(row) for row in rows]


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
    return [dict(row) for row in rows]


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
    message_text = req.message.strip()

    if not message_text:
        raise HTTPException(400, "Message is empty.")

    c = conn()
    chat_id = req.chat_id

    if chat_id:
        ok = c.execute(
            "SELECT id FROM chats WHERE id=? AND user_id=?",
            (chat_id, u["id"])
        ).fetchone()

        if not ok:
            c.close()
            raise HTTPException(404, "Chat not found.")
    else:
        created_chat = c.execute(
            """
            INSERT INTO chats(user_id,title,created_at,updated_at)
            VALUES(?,?,?,?)
            RETURNING id
            """,
            (u["id"], message_text[:60], now(), now())
        ).fetchone()
        chat_id = created_chat["id"]

    c.execute(
        """
        INSERT INTO messages(chat_id,role,content,created_at)
        VALUES(?,?,?,?)
        """,
        (chat_id, "user", message_text, now())
    )

    rows = c.execute(
        "SELECT role,content FROM messages WHERE chat_id=? ORDER BY id",
        (chat_id,)
    ).fetchall()

    c.commit()
    c.close()

    context = "\n\n".join(
        f"{row['role'].upper()}: {row['content']}"
        for row in rows
    )

    try:
        answer, model, keylabel = gemini(
            "CONVERSATION:\n" + context +
            "\n\nCURRENT USER REQUEST:\n" + message_text
        )
    except HTTPException as error:
        log(u["id"], "chat", "error", str(error.detail))
        raise

    c = conn()
    c.execute(
        """
        INSERT INTO messages(chat_id,role,content,created_at)
        VALUES(?,?,?,?)
        """,
        (chat_id, "assistant", answer, now())
    )
    c.execute(
        "UPDATE chats SET updated_at=? WHERE id=?",
        (now(), chat_id)
    )
    c.execute(
        """
        INSERT INTO usage(
            user_id,model,input_chars,output_chars,created_at
        )
        VALUES(?,?,?,?,?)
        """,
        (u["id"], model, len(message_text), len(answer), now())
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
        "chat_id": chat_id,
        "answer": answer,
        "files": extract_files(answer),
        "model": model
    }


# =========================================================
# WORKSPACE
# =========================================================

@app.get("/api/workspace/files")
def workspace_files(u=Depends(current)):
    out = []

    for path in WORKSPACE.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            out.append({
                "path": str(path.relative_to(WORKSPACE)).replace("\\", "/"),
                "size": path.stat().st_size
            })

    return sorted(out, key=lambda item: item["path"])


@app.get("/api/workspace/file")
def read_file(path: str, u=Depends(current)):
    target = safe_path(path)

    if not target.is_file():
        raise HTTPException(404, "File not found.")

    return {
        "path": path,
        "content": target.read_text(
            encoding="utf-8",
            errors="replace"
        )
    }


@app.post("/api/workspace/file")
def write_file(req: FileReq, u=Depends(current)):
    if req.content is None:
        raise HTTPException(400, "Content is required.")

    target = safe_path(req.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")

    return {"ok": True, "path": req.path}


# =========================================================
# PROJECTS
# =========================================================

@app.post("/api/projects")
def project(req: ProjectReq, u=Depends(current)):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", req.name):
        raise HTTPException(400, "Invalid project name.")

    target = WORKSPACE / req.name

    if target.exists():
        raise HTTPException(409, "Project already exists.")

    target.mkdir(parents=True)
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
    return [dict(row) for row in rows]


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
    row = c.execute(
        "SELECT active FROM api_keys WHERE id=?",
        (key_id,)
    ).fetchone()

    if not row:
        c.close()
        raise HTTPException(404, "Key not found.")

    c.execute(
        "UPDATE api_keys SET active=? WHERE id=?",
        (0 if row["active"] else 1, key_id)
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


# =========================================================
# ADMIN BRANDING
# =========================================================

@app.get("/api/admin/branding")
def admin_branding(u=Depends(admin)):
    return {"logo_data": get_setting("site_logo", "")}


@app.put("/api/admin/branding")
def update_branding(req: BrandingReq, u=Depends(admin)):
    logo = validate_image_data(req.logo_data, "logo")
    c = conn()
    c.execute(
        """INSERT INTO settings(name,value) VALUES(?,?)
           ON CONFLICT(name) DO UPDATE SET value=excluded.value""",
        ("site_logo", logo or "")
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
    return [dict(row) for row in rows]


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
    return [dict(row) for row in rows]


@app.patch("/api/admin/users/{user_id}/toggle")
def toggle_user(user_id: int, u=Depends(admin)):
    c = conn()
    row = c.execute(
        "SELECT active FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not row:
        c.close()
        raise HTTPException(404, "User not found.")

    c.execute(
        "UPDATE users SET active=? WHERE id=?",
        (0 if row["active"] else 1, user_id)
    )
    c.commit()
    c.close()
    return {"ok": True}


@app.post("/api/admin/reset-password/{user_id}")
def reset_password(user_id: int, u=Depends(admin)):
    new_password = secrets.token_urlsafe(10)

    c = conn()
    row = c.execute(
        "SELECT id FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not row:
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
    return [dict(row) for row in rows]


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
