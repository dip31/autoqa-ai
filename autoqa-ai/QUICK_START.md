# 🚀 QUICK START - ONE-CLICK AGENTQE WORKFLOW

## ✅ Dependencies Installed

All dependencies for both backend and frontend have been successfully installed.

---

## 🎯 How to Run the Application

### Option 1: Run Both Services (Recommended)

#### Terminal 1 - Start Backend (Port 5001)
```bash
cd autoqa-ai/backend
python main.py
```

You'll see:
```
Initializing SQLite database...
SQLite database initialized successfully!
 * Running on http://127.0.0.1:5001
```

#### Terminal 2 - Start Frontend (Port 3000)
```bash
cd autoqa-ai/frontend
npm start
```

You'll see the React app opening in your browser at `http://localhost:3000`

---

## 📝 First Time Setup

### 1. Access the Application
- **Frontend**: `http://localhost:3000`
- **Backend**: `http://localhost:5001` (API endpoint)

### 2. Create Account or Login
- Click "Register" if new user
- Or login with existing credentials

### 3. Navigate to Autonomous QA
- Click sidebar → "Autonomous QA"

### 4. Select AgentQE Mode
- Look for the **Pipeline Mode** toggle
- Select **"⚡ AgentQE ML"** (purple/violet button)

### 5. Fill the Form

```
Run Title:        "My First Test"
Requirement:      "Test the login page. User should be able to login with valid credentials"
Module:           "Authentication"
URL:              "https://example.com/login"
Repo URL:         (optional) "https://github.com/user/repo"
```

### 6. Click "Run AgentQE Pipeline"
- Watch the progress stepper
- See real-time logs
- View results in tabs

---

## 🎨 Understanding the UI

### Pipeline Mode Toggle
```
🤖 Standard        | ⚡ AgentQE ML
(Legacy QA)        | (ML-Enhanced)
                   |
                   | ← Use this one!
```

### Progress Tracking
```
✓ Analysis → ✓ Generation → ✓ Execution → ✓ Reporting → ✓ Completed
```

### Tabs (View Results)
- **Overview** - Summary of the run
- **Test Cases** - All generated tests
- **Browser Actions** - Real-time execution logs
- **Auto-Heal** - Self-healing statistics
- **Final Report** - Deployment verdict & recommendations
- **Repo Intel** - (Optional) Repository analysis

---

## 📊 Example Test Scenarios

### Example 1: Simple Login Test (30 seconds)
```
Title:       "Login Page Test"
Requirement: "Test login with valid username and password"
URL:         "https://demo.example.com/login"
Module:      "Auth"

Expected:
- 8-12 test cases generated
- 2-3 minutes execution
- 90%+ quality score
```

### Example 2: Without URL (Dry Run - 10 seconds)
```
Title:       "Test Planning"
Requirement: "Generate tests for user dashboard:
              - View dashboard
              - Edit profile
              - Logout"
URL:         (leave empty)
Module:      "Dashboard"

Expected:
- 5-8 test cases generated
- No browser execution
- All tests marked "Skipped"
```

---

## ⚙️ Configuration

### Backend Configuration (.env file)
Located at: `autoqa-ai/backend/.env`

Key settings:
```
FLASK_ENV=development
SECRET_KEY=your-secret-key
DATABASE=sqlite  # or mysql
PORT=5001
```

### Frontend Configuration (.env file)
Located at: `autoqa-ai/frontend/.env`

Key settings:
```
REACT_APP_API_URL=http://localhost:5001
```

---

## 🐛 Troubleshooting

### Backend Won't Start

**Error**: `ModuleNotFoundError: No module named 'mysql'`
```bash
# Solution: Install dependencies
pip install -r requirements.txt
```

**Error**: `Address already in use`
```bash
# Solution: Backend is already running on port 5001
# Kill existing process:
# Windows: taskkill /PID <pid> /F
# Or use different port: set FLASK_PORT=5002
```

### Frontend Won't Start

**Error**: `npm ERR! not found: make`
```bash
# On Windows, this is usually fine, ignore and run:
npm start
```

**Error**: Port 3000 already in use
```bash
# Use different port:
PORT=3001 npm start
```

### Application Won't Connect

**Error**: Cannot connect to backend
- Verify backend is running: `http://localhost:5001`
- Check `REACT_APP_API_URL` in frontend .env file
- Check browser console for CORS errors

**Error**: Database errors
- Backend uses SQLite by default (no setup needed)
- Check `autoqa-ai/backend/database/autoqa.db` exists
- Logs are in backend terminal output

---

## 🔍 Checking if Everything Works

### ✅ Backend Health Check
```bash
curl http://localhost:5001/auth/me
# Should show 401 (no token) - that's normal
```

### ✅ Frontend Health Check
- Open `http://localhost:3000`
- Should load the login page

### ✅ Full Workflow Check
1. Register/Login
2. Go to Autonomous QA
3. Toggle to "AgentQE ML"
4. Fill form with valid URL
5. Click "Run AgentQE Pipeline"
6. Watch progress appear

---

## 📚 What Happens During Execution

### Stage 1-2: Understanding (5-10 seconds)
```
✓ STRATEGY: Test types planned
✓ BROWSER: Page crawled and analyzed
```

### Stage 3-5: Generation (5-10 seconds)
```
✓ GENERATION: User tests created (10-20 tests)
✓ POOL: Engineering tests merged
✓ ENRICHMENT: Metadata added
```

### Stage 6-8: Optimization (5 seconds)
```
✓ RANKING: ML scores tests (untrained)
✓ SELECTION: Top tests selected
```

### Stage 9-13: Execution (20-60 seconds)
```
✓ EXECUTION: Browser runs tests
✓ FAILURE_ANALYSIS: Failures analyzed
✓ RISK_ANALYSIS: Risk computed
✓ REPORT: Final report generated
```

### Total Time: 40-100 seconds depending on URL complexity

---

## 🎯 Next Steps

### After First Run
1. Check "Final Report" tab
2. Review quality score
3. Understand recommendations
4. Check "Auto-Heal" tab for healing events

### Test Different Scenarios
- Try different URLs
- Try with repository URL
- Try without URL (dry run)
- Increase max_cycles for multi-cycle testing

### Share Results
- Use "Send to Dev" button in Final Report
- Share with team members
- Export results if needed

---

## 📖 Additional Documentation

For more details, read:
- **AGENTQE_USER_GUIDE.md** - Complete user manual
- **ONE_CLICK_WORKFLOW_IMPLEMENTATION.md** - Technical details
- **AGENTQE_WORKFLOW_DIAGRAM.md** - Visual diagrams

---

## 🆘 Getting Help

### Check Logs
```bash
# Backend terminal will show:
# - Stage execution logs
# - Browser actions
# - Errors with timestamps

# Frontend browser console (F12):
# - Network errors
# - API response issues
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Port 5001 in use | Kill process or use PORT=5002 python main.py |
| Port 3000 in use | Kill process or use PORT=3001 npm start |
| Database error | Delete `autoqa.db` and restart backend |
| CORS errors | Check backend is running on http://localhost:5001 |
| Tests not running | Provide valid URL in form |

---

## 🎉 You're Ready!

**The one-click AgentQE workflow is now ready to use.**

Start the services and begin testing! 🚀

---

**Quick Start Version**: 1.0  
**Status**: ✅ READY TO USE  
**Last Updated**: 2026-09-25
