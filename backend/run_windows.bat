@echo off
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
if not exist .env copy .env.example .env
python -m uvicorn app:app --host 0.0.0.0 --port 8000
