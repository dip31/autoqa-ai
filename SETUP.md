# AutoQA AI — Setup & Run Guide

## Prerequisites
- Python 3.11+
- Node.js 18+
- API keys: Groq and Gemini

---

## Backend Setup

```bash
cd autoqa-ai/backend

# 1. Create .env from the example
cp .env.example .env
# Edit .env and fill in GROQ_API_KEY, GEMINI_API_KEY, SECRET_KEY

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browser (for website testing)
playwright install chromium

# 4. Run the backend (auto-initializes the SQLite DB on first start)
python main.py
# Backend runs on http://localhost:5000
```

---

## Frontend Setup

```bash
cd autoqa-ai/frontend

# 1. Install dependencies
npm install

# 2. Start the dev server
npm start
# Frontend runs on http://localhost:3000
```

---

## Docker (Full Stack)

```bash
cd autoqa-ai

# Copy and fill backend env
cp backend/.env.example backend/.env

# Build and run both services
docker-compose up --build
# Backend: http://localhost:5000
# Frontend: http://localhost:3000
```

---

## Required Environment Variables (backend/.env)

| Variable              | Required | Description                        |
|-----------------------|----------|------------------------------------|
| `GROQ_API_KEY`        | Yes      | Groq LLaMA — code/test/risk agents |
| `GEMINI_API_KEY`      | Yes      | Gemini AI — chat, reports, diagrams|
| `SECRET_KEY`          | Yes      | JWT signing secret                 |
| `DB_HOST`             | No       | Leave blank to use local SQLite    |
| `GITHUB_CLIENT_ID`    | No       | GitHub OAuth (optional feature)    |
| `GITHUB_CLIENT_SECRET`| No       | GitHub OAuth (optional feature)    |
