# NG INTELLIGENCE — Complete Web Edition

A standalone premium web implementation of the uploaded NG/LW MINHAZ CODEX engine.

## Included
- Premium dark landing page
- Email/password registration and login
- JWT authentication
- Forgot-password-ready architecture (admin reset endpoint included)
- User dashboard and private chat history
- Gemini REST integration
- Multiple Gemini API keys with encrypted-at-rest storage
- Key enable/disable/delete
- Automatic active-key fallback
- Admin control center
- Model + system prompt settings
- Usage counters and request logs
- Workspace file browser
- Project creation
- AI file extraction using `<FILE path="...">...</FILE>`
- Auto Debug / Auto Fix workflow
- Markdown/code response rendering
- Responsive desktop/mobile interface
- Rate limiting
- Server-side secrets only
- Docker support

## Important deployment note
Do not expose arbitrary shell execution to an untrusted public website. The original
terminal engine has `/run`; this web edition keeps that capability disabled by default.
If you enable it for a private development machine, isolate the process/container first.

## Quick start

### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Set `GEMINI_API_KEY`, `JWT_SECRET`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` in `.env`.

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` if the backend is not at `http://localhost:8000`.

### Docker
```bash
docker compose up --build
```

## Production checklist
- Use HTTPS.
- Replace SQLite with PostgreSQL for multi-instance production.
- Put the backend behind a reverse proxy.
- Set a long random `JWT_SECRET`.
- Set `CORS_ORIGINS` to the exact frontend domain.
- Keep Gemini keys only on the backend.
- Back up the database.
- Do not enable remote command execution unless isolated in a sandbox/container.
