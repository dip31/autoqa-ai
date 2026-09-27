# AgentQE ONE-CLICK WORKFLOW - USER GUIDE

## 🎯 Quick Start (5 Steps)

### Step 1: Login
Navigate to `http://localhost:3000` and login with your credentials.

### Step 2: Go to Autonomous QA
Click on "Autonomous QA" in the sidebar navigation.

### Step 3: Select AgentQE Mode
Toggle the pipeline mode to **"⚡ AgentQE ML"** (purple/violet button).

### Step 4: Fill the Form
```
Run Title: "User Login Flow Test"
Requirement: "Verify that users can successfully login with valid credentials and see error messages for invalid attempts"
Module: "Authentication"
URL: "https://your-app.com/login"
Repo URL: "https://github.com/yourorg/yourrepo" (optional)
```

### Step 5: Click Run
Click the **"Run AgentQE Pipeline"** button and watch the magic happen!

---

## 📋 Form Fields Explained

### Required Fields

**Run Title**
- Short descriptive name for this test run
- Example: "Dashboard Navigation Test", "Checkout Flow Test"

**Requirement / User Story**
- Detailed description of what should be tested
- Can be a user story, feature description, or test scenario
- The AI uses this to generate relevant test cases
- Example: "As a user, I want to add items to cart, apply a discount code, and complete checkout"

### Optional Fields

**Module**
- The application module/component being tested
- Examples: "Frontend", "Dashboard", "Payment", "Authentication"
- Default: "General"

**URL**
- Starting URL for browser-based testing
- If provided, the system will crawl the page and extract real selectors
- If omitted, tests will be generated in "dry-run" mode

**Git Repository URL**
- GitHub repository URL for code intelligence
- If provided, adds repository analysis to the workflow
- Helps identify architectural patterns and risk areas
- Format: `https://github.com/user/repo`

---

## 🎨 Understanding the UI

### Pipeline Mode Toggle
| Mode | Description | Use When |
|------|-------------|----------|
| 🤖 **Standard** | Legacy autonomous QA pipeline | Quick test generation without ML |
| ⚡ **AgentQE ML** | Full ML-enhanced workflow | Complete end-to-end ML pipeline |

### Progress Stepper
Shows current stage of execution:
```
Analysis → Generation → Execution → Reporting → Completed
```

Each stage lights up as the workflow progresses.

### AgentQE ML Pipeline Stages
Real-time display of ML pipeline stages:
- ✅ **STRATEGY** - Test strategy planned
- ✅ **GENERATION** - Tests generated
- ✅ **POOL** - Tests merged
- ✅ **ENRICHMENT** - Metadata added
- ✅ **RANKING** - ML scoring (untrained)
- ✅ **SELECTION** - Top tests selected
- ✅ **EXECUTION** - Browser tests running
- ✅ **FAILURE_ANALYSIS** - Failures analyzed
- ✅ **PIPELINE** - Complete

### Tabs

**Overview**
- Feature intent summary
- Extracted scope items
- High-level run information

**Test Cases**
- All generated test cases
- Status indicators (PASS, FAIL, HEALED, BLOCKED)
- Test metadata (priority, type, generated_by)

**Browser Actions**
- Real-time execution logs
- Terminal-style display
- Shows each action with timestamp and status

**Auto-Heal**
- Self-healing statistics
- Detailed healing analysis
- Original vs suggested selectors
- Confidence scores

**Final Report**
- Deployment verdict
- Executive summary
- Risk analysis
- High-risk areas
- Strategic recommendations
- Share button (send to developer)

**Repo Intel** (if repo URL provided)
- Tech stack analysis
- Architectural quality metrics
- AI-identified bug risks

---

## 📊 Reading the Results

### Quality Score
```
90-100% = Excellent - Ready for deployment
70-89%  = Good - Minor issues to address
50-69%  = Fair - Significant issues found
0-49%   = Poor - Major problems detected
```

### Test Status

| Status | Meaning |
|--------|---------|
| **PASS** | Test executed successfully |
| **HEALED** | Test failed but auto-healed successfully |
| **FAIL** | Test failed and could not be healed |
| **BLOCKED** | Test could not run (dependency issue) |
| **Skipped** | Test generated but not selected for execution |

### Auto-Healing

**What is Auto-Healing?**
When a test fails due to a broken selector (UI element not found), the system automatically:
1. Detects the failure
2. Searches for similar elements on the page
3. Finds the best match using AI
4. Retries the test with the new selector
5. Marks as HEALED if successful

**Healing Stats**
- **Total Failures**: Number of selector failures detected
- **Successfully Healed**: Number of auto-recoveries
- **Heal Success Rate**: Percentage of successful healings
- **Unresolved**: Failures that couldn't be healed

### Risk Analysis

**Module Risk Score**
- Inverse of quality score (100 - quality_score)
- Lower is better
- Indicates overall risk level

**Release Readiness**
- "Ready" - Quality score ≥ 70%
- "Not Ready" - Quality score < 70%

**High-Risk Areas**
- Specific test scenarios that failed
- Areas requiring attention before deployment

**Recommendations**
- Actionable suggestions based on results
- Prioritized list of improvements

---

## 🔍 Advanced Features

### Sharing Reports with Developers

1. Complete a test run
2. Navigate to "Final Report" tab
3. Click "Send to Dev" button
4. Select developer from dropdown
5. Click "Confirm & Send Report"
6. Developer receives message with full report

### Viewing Run History

All runs are saved and accessible:
1. Check "Recent Runs" sidebar on the left
2. Click any run to view details
3. Run status badges show current state
4. Completed runs can be reviewed anytime

### Understanding Logs

**Log Format**
```
[Timestamp] [STATUS] [ACTION_TYPE] Description
```

**Example**
```
14:23:45 [SUCCESS] [BROWSER] Crawled: Login Page
14:23:48 [INFO] [GENERATION] User-perspective generator: 12 test cases created
14:24:10 [SUCCESS] [EXECUTION] Browser execution complete with self-healing
```

---

## ⚠️ Known Limitations

### 1. ML Ranking (Untrained)
**What it means**: The Transformer model that scores tests is not yet trained with real data.

**Impact**: Test prioritization uses random ML scores, not learned patterns.

**Fallback**: Rule-based prioritization works reliably.

**UI Label**: "UNTRAINED MODEL" warning shown in logs.

### 2. Engineering Tests (Stub)
**What it means**: Engineering test generation returns only 1 sample UNIT test.

**Impact**: API and Security tests are not automatically generated yet.

**Workaround**: User tests (UI flows) are fully functional.

**UI Label**: "(STUB - currently returns sample unit test)" warning shown.

### 3. No Automatic Re-Test
**What it means**: If quality evaluation decides "REPLAN", it's logged but doesn't auto-restart.

**Impact**: You must manually start a new run to re-test.

**Workaround**: Check quality decision in logs, then create new run if needed.

### 4. Human Review (Non-Blocking)
**What it means**: Submitting a review saves your decision but doesn't pause/restart execution.

**Impact**: Review is post-execution, not a blocking approval.

**Workaround**: Use reviews for audit trails and team communication.

---

## 🐛 Troubleshooting

### "Execution failed" Error
**Possible Causes**:
- Invalid URL format
- URL not accessible
- Browser automation blocked
- Network timeout

**Solutions**:
1. Verify URL is correct and accessible
2. Check if site allows automation
3. Try a different URL
4. Check backend logs for details

### Tests Generated But No Execution
**Cause**: No URL provided

**Solution**: Tests are in "dry-run" mode. Add a URL to enable browser execution.

### Polling Stops / UI Not Updating
**Cause**: Network error or max consecutive errors (3)

**Solutions**:
1. Refresh the page
2. Click the run in "Recent Runs" to reload
3. Check browser console for errors
4. Verify backend is running

### "Run not found" Error
**Causes**:
- Run belongs to different user
- Run was deleted
- Invalid run_id

**Solution**: Check "Recent Runs" for available runs.

---

## 💡 Best Practices

### Writing Requirements

**Good Example**:
```
Test the user registration flow:
1. User navigates to signup page
2. Fills in username, email, password
3. Submits the form
4. Receives confirmation email
5. Verifies email and activates account

Include negative tests for:
- Invalid email format
- Weak password
- Duplicate username
```

**Why it's good**:
- Clear step-by-step flow
- Specific actions mentioned
- Includes negative cases
- Easy for AI to understand

**Poor Example**:
```
Test the app
```

**Why it's poor**:
- Too vague
- No specific actions
- AI will generate generic tests

### Choosing Module Names

Use descriptive, consistent names:
- ✅ "User Authentication"
- ✅ "Shopping Cart"
- ✅ "Payment Processing"
- ❌ "Thing"
- ❌ "Test123"

### URL Selection

**Best URLs to test**:
- Login pages
- Forms (registration, checkout, contact)
- Dashboards with multiple interactions
- Search interfaces
- Multi-step wizards

**URLs to avoid**:
- CAPTCHAs
- Sites that block automation
- Complex SPAs without proper selectors

---

## 📈 Interpreting Results for Decision-Making

### Scenario 1: High Quality Score (90%+)
**Interpretation**: Excellent test coverage, all critical flows passing.

**Action**: ✅ Ready for deployment

**Next Steps**:
- Share report with team
- Proceed to staging/production
- Monitor in production

### Scenario 2: Good Score with Healing (70-89%)
**Interpretation**: Tests passed but required auto-healing. UI may be unstable.

**Action**: ⚠️ Review healing logs before deploying

**Next Steps**:
- Check "Auto-Heal" tab
- Review suggested selectors
- Update code with stable selectors
- Consider running tests again

### Scenario 3: Low Score (Below 70%)
**Interpretation**: Significant issues detected.

**Action**: ❌ Do not deploy

**Next Steps**:
- Review "Final Report" recommendations
- Fix identified high-risk areas
- Address failing tests
- Run workflow again after fixes

### Scenario 4: REPLAN Decision
**Interpretation**: Quality agent suggests another cycle.

**Action**: 🔄 Consider re-running with adjusted approach

**Next Steps**:
- Review failures in detail
- Adjust requirements or URL if needed
- Start new run with improvements
- Compare results across runs

---

## 🎓 Example Workflows

### Example 1: Testing a Login Page

```
Title: "Login Functionality Verification"

Requirement:
"Test the login page at /login:
- Valid credentials should redirect to dashboard
- Invalid credentials show error message
- Empty fields show validation errors
- Remember me checkbox persists session
- Forgot password link navigates correctly"

Module: "Authentication"

URL: "https://yourapp.com/login"
```

**Expected Results**:
- 8-12 test cases generated
- Mix of positive and negative tests
- Browser executes login attempts
- Self-healing if button selectors changed
- Quality score reflects login reliability

### Example 2: Testing a Checkout Flow

```
Title: "E-commerce Checkout End-to-End"

Requirement:
"Test the complete checkout process:
1. Add product to cart
2. Proceed to checkout
3. Enter shipping information
4. Select payment method
5. Apply discount code
6. Review order summary
7. Place order
8. Verify confirmation page

Test edge cases:
- Empty cart checkout
- Invalid discount codes
- Incomplete address
- Payment failures"

Module: "Checkout"

URL: "https://yourshop.com/products"
```

**Expected Results**:
- 15-20 test cases covering happy path + edge cases
- Multi-page navigation testing
- Form validation tests
- Quality score indicates checkout reliability

### Example 3: Testing Without a URL (Dry Run)

```
Title: "API Specification Review"

Requirement:
"Generate test cases for the User Management API:
- POST /api/users (create user)
- GET /api/users/:id (get user)
- PUT /api/users/:id (update user)
- DELETE /api/users/:id (delete user)

Include tests for:
- Successful operations
- Invalid data
- Unauthorized access
- Resource not found"

Module: "API"

URL: (leave empty)
```

**Expected Results**:
- Test cases generated based on requirement
- No browser execution (dry run)
- All tests marked as "Skipped"
- Useful for test planning phase

---

## 🔄 Multi-Cycle Testing

The AgentQE pipeline supports multiple cycles (`max_cycles` parameter, default: 3).

**How it works**:
1. First cycle executes and evaluates
2. If failures detected AND cycles remain:
   - Quality agent logs "REPLAN"
3. Currently: Auto-replan NOT triggered
4. Future: System will automatically adapt and re-test

**Manual Multi-Cycle Process**:
1. Run AgentQE pipeline (Cycle 1)
2. Review results and failures
3. Update requirement based on findings
4. Run again (Cycle 2)
5. Compare results across cycles

---

## 📞 Getting Help

### Check Logs
1. Navigate to "Browser Actions" tab
2. Look for ERROR or FAIL status entries
3. Copy error messages for debugging

### Backend Logs
```bash
# In backend directory
tail -f logs/app.log  # if logging to file
# OR check terminal where app.py is running
```

### Frontend Console
```
Open browser DevTools (F12)
Check Console tab for errors
Check Network tab for failed API calls
```

---

## 🚀 Next Steps After Testing

### If Tests Pass
1. ✅ Share report with team
2. 📋 Document test coverage
3. 🚀 Deploy with confidence
4. 📊 Set up monitoring

### If Tests Fail
1. 🔍 Analyze failure patterns
2. 🛠️ Fix identified issues
3. 🔄 Re-run tests
4. ✅ Verify fixes worked

### Continuous Improvement
1. 📈 Track quality scores over time
2. 🎯 Improve test requirements
3. 🤖 Monitor healing rates
4. 📝 Update selectors based on healing suggestions

---

## 📚 Related Documentation

- `ONE_CLICK_WORKFLOW_IMPLEMENTATION.md` - Technical implementation details
- `AGENTQE_WORKFLOW_DIAGRAM.md` - Visual workflow diagrams
- `AGENTQE_AUDIT_REPORT.md` - System audit and capabilities
- `SETUP.md` - Installation and setup instructions

---

**Guide Version**: 1.0  
**Last Updated**: 2026-09-25  
**Status**: ✅ PRODUCTION-READY
