# AutoQA AI — Intelligent QA Automation Platform

## Project Structure
```
autoqa-ai/
├── backend/
│   ├── app.py                  # Flask API server
│   ├── requirements.txt
│   ├── .env.example
│   ├── agents/
│   │   ├── testcase_agent.py
│   │   ├── code_agent.py
│   │   ├── website_agent.py
│   │   ├── generator_agent.py
│   │   ├── risk_agent.py
│   │   └── report_agent.py
│   └── database/
│       ├── db.py
│       └── schema.sql
└── frontend/
    ├── package.json
    ├── tailwind.config.js
    └── src/
        ├── App.jsx
        ├── api/client.js
        ├── components/
        │   ├── Sidebar.jsx
        │   ├── Loader.jsx
        │   ├── ScoreBadge.jsx
        │   └── ErrorAlert.jsx
        └── pages/
            ├── Dashboard.jsx
            ├── TestCaseReview.jsx
            ├── CodeReview.jsx
            ├── WebsiteTesting.jsx
            ├── TestGenerator.jsx
            ├── RiskPrediction.jsx
            └── SmartReport.jsx
```

## Setup Instructions

### 1. Database
```sql
mysql -u root -p < backend/database/schema.sql
```

### 2. Backend
```bash
cd backend
cp .env.example .env
# Fill in your API keys and DB credentials in .env

pip install -r requirements.txt
playwright install chromium

python app.py
# Runs on http://localhost:5000
```

### 3. Frontend
```bash
cd frontend
npm install
npm start
# Runs on http://localhost:3000
```

## API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /review-testcase | Analyze a manual test case |
| POST | /review-code | Review code quality |
| POST | /website-test | Analyze a website URL |
| POST | /generate-testcase | Generate test cases from requirements |
| POST | /predict-risk | Predict bug risk |
| GET  | /generate-report | Generate smart QA report |

## Environment Variables
```
OPENAI_API_KEY=your_key
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=autoqa_db
```
