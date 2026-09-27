# AgentQE One-Click Workflow Testing Guide

## Pre-Test Checklist

### Backend Requirements

1. **Python Environment**
   ```bash
   cd autoqa-ai/backend
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Environment Variables**
   - Ensure `.env` file exists with `GEMINI_API_KEY`

3. **Database**
   - SQLite database should exist at `database/autoqa.db`
   - Run migrations if needed: `python database/init_db.py`

4. **Start Backend**
   ```bash
   cd autoqa-ai/backend
   python app.py
   # Should start on http://localhost:5001
   ```

### Frontend Requirements

1. **Node Environment**
   ```bash
   cd autoqa-ai/frontend
   npm install
   ```

2. **Environment Variables**
   - Create/check `.env` file:
     ```
     REACT_APP_API_URL=http://localhost:5001
     ```

3. **Start Frontend**
   ```bash
   cd autoqa-ai/frontend
   npm start
   # Should start on http://localhost:3000
   ```

## Test Scenarios

### Test 1: Basic AgentQE Run (No URL)

**Purpose:** Verify pipeline runs without browser execution

**Steps:**
1. Navigate to http://localhost:3000
2. Login with test credentials
3. Click "Autonomous QA" in sidebar
4. Fill form:
   - Title: "Dry Run Test"
   - Requirement: "Test authentication flow with login and registration"
   - Module: "Auth"
   - URL: (leave empty)
   - Repo URL: (leave empty)
5. Select "AgentQE ML" mode
6. Click "Run AgentQE Pipeline"

**Expected Results:**
- ✅ Run created with status "Starting"
- ✅ Status changes: Starting → Analysis → Generation → Execution → Reporting → Completed
- ✅ Logs show:
  - `STRATEGY` entries
  - `GENERATION` entries (User + Engineering)
  - `POOL` entries
  - `ENRICHMENT` entries
  - `RANKING` entries (with UNTRAINED warning)
  - `SELECTION` entries
  - `EXECUTION` entries (dry run warning)
  - `FAILURE_ANALYSIS` entries
  - `QUALITY_EVAL` entries
  - `RISK_ANALYSIS` entries
  - `REPORT` entries
  - `PIPELINE` entries
- ✅ Test cases generated (20-30 tests)
- ✅ All tests marked as "PASS" (dry run)
- ✅ Report generated with verdict
- ✅ AgentQE stage detail shows completed stages

**Acceptable Warnings:**
- "UNTRAINED MODEL" in RANKING log
- "Engineering tests: 1 case (STUB)" in GENERATION log
- "No URL — dry run mode" in EXECUTION log

### Test 2: AgentQE Run with Live URL

**Purpose:** Verify full browser execution with self-healing

**Steps:**
1. Click "New Run"
2. Fill form:
   - Title: "Google Search Test"
   - Requirement: "Test Google search functionality and navigation"
   - Module: "Search"
   - URL: "https://www.google.com"
   - Repo URL: (leave empty)
3. Select "AgentQE ML" mode
4. Click "Run AgentQE Pipeline"

**Expected Results:**
- ✅ Run created
- ✅ Status progresses through all stages
- ✅ Logs show:
  - `BROWSER` and `CRAWL` entries with page structure
  - `BROWSER_ACTION` entries with actual browser interactions
  - Test results with mixed statuses: PASS, HEALED, FAIL, Blocked
- ✅ Auto-Heal tab shows healing attempts
- ✅ Some tests marked as "Blocked" (require authentication)
- ✅ Some tests may show "HEALED" status
- ✅ Final report with actual execution metrics

**Acceptable Behaviors:**
- Some tests blocked due to auth requirements
- Some tests may fail (expected for negative tests)
- Healing may or may not succeed (depends on page structure)

### Test 3: AgentQE with Repository URL

**Purpose:** Verify repo intelligence integration

**Steps:**
1. Click "New Run"
2. Fill form:
   - Title: "Repo Intelligence Test"
   - Requirement: "Analyze repository structure and test coverage"
   - Module: "Full Stack"
   - URL: (leave empty)
   - Repo URL: "https://github.com/facebook/react"
3. Select "AgentQE ML" mode
4. Click "Run AgentQE Pipeline"

**Expected Results:**
- ✅ Run created
- ✅ Status shows "Repo Scan" stage
- ✅ Logs show `REPO_SCAN` entries
- ✅ If successful: Repo intelligence data appears in "Repo Intel" tab
- ✅ If failed: Warning logged, pipeline continues without repo data
- ✅ Pipeline completes even if repo scan fails

### Test 4: UI Feature Validation

**Purpose:** Verify all UI components display correctly

**Steps:**
1. Run any AgentQE workflow (Test 1 or 2)
2. Wait for completion
3. Check each tab

**Expected UI Elements:**

**Overview Tab:**
- ✅ Feature Intent section with requirement summary
- ✅ Extracted Scope with bullet points
- ✅ 5-stage stepper visualization
- ✅ AgentQE stage detail box (violet background)
- ✅ Stage list showing: STRATEGY, GENERATION, POOL, ENRICHMENT, RANKING, SELECTION, EXECUTION, FAILURE_ANALYSIS

**Test Cases Tab:**
- ✅ Table with all generated tests
- ✅ Test ID, Scenario, Status, Priority columns
- ✅ Category badges (UI, Functional, Negative, etc.)
- ✅ Auto-Healed badges where applicable

**Browser Actions Tab:**
- ✅ Terminal-style log display (dark background)
- ✅ Timestamps, status, action type, detail
- ✅ Auto-Heal trigger markers

**Auto-Heal Tab:**
- ✅ Summary cards: Total Failures, Successfully Healed, Heal Success Rate, Unresolved
- ✅ Detailed healing analysis cards
- ✅ Original selector vs. Healed selector comparison
- ✅ Healing stage and confidence score

**Final Report Tab:**
- ✅ Executive summary
- ✅ Quality score badge
- ✅ Test statistics
- ✅ Risk analysis
- ✅ Recommendations

**Repo Intel Tab** (if repo_url provided):
- ✅ Tech stack information
- ✅ Repository structure
- ✅ Test coverage analysis

### Test 5: Standard vs AgentQE Mode Comparison

**Purpose:** Verify both modes work and produce different results

**Steps:**
1. Run Test 1 with "Standard" mode
2. Run Test 1 with "AgentQE ML" mode
3. Compare results

**Expected Differences:**

**Standard Mode:**
- Uses `run_autonomous_qa` orchestration
- Simpler log structure
- No ML ranking stage
- No multi-perspective generation
- No candidate pool

**AgentQE ML Mode:**
- Uses `run_agentqe_pipeline` orchestration
- Detailed stage logging
- ML ranking (with UNTRAINED warning)
- User + Engineering tests
- Candidate pool merging
- AgentQE stage detail visible in UI

### Test 6: Error Handling

**Purpose:** Verify graceful error handling

**Test Cases:**

**6a. Invalid URL**
- URL: "not-a-valid-url"
- Expected: Pipeline handles error, logs failure, continues where possible

**6b. Unreachable URL**
- URL: "https://this-domain-definitely-does-not-exist-12345.com"
- Expected: Crawl fails with error log, pipeline may continue with dry run

**6c. Missing GEMINI_API_KEY**
- Remove API key from .env
- Expected: Generation stage fails, error logged, run status = "Failed"

**6d. Database Error**
- Make database read-only
- Expected: Logs show DB errors, graceful failure

### Test 7: Concurrent Runs

**Purpose:** Verify multiple runs can execute simultaneously

**Steps:**
1. Start Run A (with URL)
2. Immediately start Run B (different requirement)
3. Monitor both runs

**Expected Results:**
- ✅ Both runs progress independently
- ✅ Logs don't interleave incorrectly
- ✅ Each run has separate run_id
- ✅ Both complete successfully

### Test 8: History and Navigation

**Purpose:** Verify run history and navigation

**Steps:**
1. Complete 3-5 AgentQE runs
2. Check "Recent Runs" sidebar
3. Click on older runs
4. Navigate between runs

**Expected Results:**
- ✅ All runs listed in chronological order
- ✅ Each run shows title and status badge
- ✅ Clicking run loads its details
- ✅ Active run highlighted
- ✅ Completed runs show full results
- ✅ Failed runs show error state

### Test 9: Human Review (Partial)

**Purpose:** Verify review submission (orchestration not active)

**Steps:**
1. Complete an AgentQE run
2. Open browser console
3. Call review API:
   ```javascript
   fetch('http://localhost:5001/api/agentqe/review/1', {
     method: 'POST',
     headers: {
       'Authorization': 'Bearer ' + localStorage.getItem('token'),
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({
       decision: 'APPROVE',
       feedback: 'Tests look good',
       cycle: 1
     })
   }).then(r => r.json()).then(console.log)
   ```

**Expected Results:**
- ✅ API returns success
- ✅ Review saved to database
- ⚠️ Pipeline does NOT restart (expected limitation)
- ⚠️ No visible UI change (expected limitation)

## Success Criteria

### Must Pass (Critical)

- [ ] Backend starts without errors
- [ ] Frontend loads successfully
- [ ] User can login
- [ ] AgentQE run can be created
- [ ] Pipeline executes all stages
- [ ] Logs appear in database
- [ ] Test cases generated and saved
- [ ] Status updates reflect progress
- [ ] UI shows real-time updates via polling
- [ ] Run completes with "Completed" status
- [ ] Report generated and displayed
- [ ] Existing autonomous QA features still work

### Should Pass (Important)

- [ ] Browser execution works with URL
- [ ] Self-healing attempts visible
- [ ] Repo intelligence runs (if URL provided)
- [ ] AgentQE stage detail renders
- [ ] All tabs display correctly
- [ ] Multiple concurrent runs work
- [ ] Error states handled gracefully
- [ ] Standard mode still functions

### May Fail (Known Limitations - Acceptable)

- [ ] Transformer ranking (UNTRAINED warning expected)
- [ ] Engineering test generation (stub expected)
- [ ] Re-test loop (not implemented)
- [ ] Human review orchestration (partial)
- [ ] Historical learning (heuristic only)
- [ ] Docker sandbox (not functional)

## Debugging Tips

### Backend Issues

**Check logs:**
```bash
cd autoqa-ai/backend
tail -f app.log  # if logging to file
# or check terminal output
```

**Check database:**
```bash
cd autoqa-ai/backend/database
sqlite3 autoqa.db
> SELECT * FROM autonomous_runs ORDER BY created_at DESC LIMIT 5;
> SELECT * FROM autonomous_execution_logs WHERE run_id=1 ORDER BY timestamp;
```

**Test individual components:**
```python
# In Python REPL
from agentqe.pipeline import run_agentqe_pipeline
run_agentqe_pipeline(1)  # Test with existing run_id
```

### Frontend Issues

**Check browser console:**
- Look for API errors (401, 500, etc.)
- Check network tab for failed requests
- Verify polling is active

**Check localStorage:**
```javascript
console.log('Token:', localStorage.getItem('token'));
console.log('User:', localStorage.getItem('user'));
```

**Test API directly:**
```bash
# Get run details
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:5001/api/autonomous-qa/run/1

# Start run
curl -X POST \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","requirement_text":"Test auth","execution_mode":"AgentQE Pipeline","max_cycles":3}' \
  http://localhost:5001/api/agentqe/run
```

### Common Issues

**Issue:** Pipeline hangs at "Starting"
**Solution:** Check backend logs for Python exceptions

**Issue:** No logs appearing in UI
**Solution:** Check database permissions, verify polling interval

**Issue:** Playwright crashes
**Solution:** `playwright install chromium`, check system dependencies

**Issue:** "Cannot read property 'run' of null"
**Solution:** Run hasn't loaded yet, wait for API response

**Issue:** UI shows "Failed" immediately
**Solution:** Check backend logs for startup errors (missing env vars, etc.)

## Performance Benchmarks

Expected execution times:

| Scenario | Expected Duration |
|----------|------------------|
| Dry run (no URL) | 10-30 seconds |
| With URL + 20 tests | 1-3 minutes |
| With URL + 40 tests | 2-5 minutes |
| Repo scan + tests | 2-4 minutes |

Factors affecting duration:
- Gemini API latency (1-5s per call)
- Browser page load times
- Number of tests generated
- Healing attempts required
- Network conditions

## Test Report Template

```
AgentQE Workflow Test Report
Date: ____________
Tester: ____________

Test Environment:
- Backend: Python 3.x, Flask 2.3
- Frontend: React 18
- Browser: Chrome/Chromium
- OS: __________

Test Results:

Test 1 (Dry Run): [ PASS / FAIL ]
  Notes: _______________________

Test 2 (Live URL): [ PASS / FAIL ]
  Notes: _______________________

Test 3 (Repo URL): [ PASS / FAIL ]
  Notes: _______________________

Test 4 (UI Validation): [ PASS / FAIL ]
  Notes: _______________________

Test 5 (Mode Comparison): [ PASS / FAIL ]
  Notes: _______________________

Test 6 (Error Handling): [ PASS / FAIL ]
  Notes: _______________________

Test 7 (Concurrent): [ PASS / FAIL ]
  Notes: _______________________

Test 8 (Navigation): [ PASS / FAIL ]
  Notes: _______________________

Known Issues Found:
1. _______________________
2. _______________________

Recommendations:
1. _______________________
2. _______________________

Overall Assessment: [ PASS / FAIL / PARTIAL ]
```

## Acceptance Criteria

The AgentQE one-click workflow is considered **PASSING** if:

✅ All "Must Pass" criteria are met  
✅ At least 80% of "Should Pass" criteria are met  
✅ Known limitations are clearly documented  
✅ No data loss or corruption occurs  
✅ Existing features continue working  
✅ UI accurately reflects backend state  
✅ Error messages are meaningful  
✅ Documentation matches reality  

The workflow is considered **PRODUCTION READY** when:

✅ All tests pass  
✅ Performance within acceptable range  
✅ No critical bugs found  
✅ User feedback positive  
✅ Edge cases handled  
✅ Monitoring/logging adequate  
