# 🧪 PUBLIC TEST SITES FOR AGENTQE AUTONOMOUS QA

## Overview

This guide provides public websites you can use to test the AgentQE ML pipeline with realistic test scenarios and requirements.

---

## ✅ RECOMMENDED TEST SITES

### 1. **Swag Labs Demo Store** (E-Commerce)

**URL:** https://www.saucedemo.com

**Credentials:**
- Username: `standard_user`
- Password: `secret_sauce`

**Key Features:**
- Shopping cart functionality
- Product filtering
- User authentication
- Checkout flow
- Social login links

**Test Scenarios:**

#### Scenario 1: User Shopping Flow
```
Title: Complete Shopping Flow
Requirement: 
"Test the complete e-commerce shopping experience:
1. User logs in with valid credentials
2. Browse products and apply filters (price, A-Z)
3. Add multiple items to cart
4. View cart contents
5. Proceed to checkout
6. Fill shipping information
7. Complete payment
8. View order confirmation

Include negative tests for:
- Login with invalid credentials
- Checkout with incomplete address
- Payment processing errors"

URL: https://www.saucedemo.com
Module: E-Commerce Platform
```

#### Scenario 2: Product Browsing
```
Title: Product Filtering and Search
Requirement:
"Test product discovery features:
1. Navigate to all products page
2. Apply price filter (low to high)
3. Sort by name (A-Z)
4. Add filtered products to cart
5. Verify cart totals
6. Apply promo codes
7. Calculate final prices with tax

Edge cases:
- Filter with no results
- Sort with single product
- Price range validation
- Currency formatting"

URL: https://www.saucedemo.com
Module: Product Management
```

---

### 2. **OpenCart Demo Store**

**URL:** https://demo.opencart.com

**Key Features:**
- Full e-commerce platform
- Product catalog
- User accounts
- Shopping cart
- Wishlist
- Order management
- Customer reviews

**Test Scenarios:**

#### Scenario 1: Account Management
```
Title: User Account Registration and Management
Requirement:
"Test complete account lifecycle:
1. Create new customer account
2. Verify email confirmation
3. Login with new account
4. Update profile information
5. Change password
6. Add delivery addresses
7. View order history
8. Manage wishlist
9. Update email preferences
10. Delete account

Validate:
- Required field validation
- Email format validation
- Password strength requirements
- Address form validation
- Duplicate account prevention"

URL: https://demo.opencart.com
Module: User Management
```

#### Scenario 2: Shopping and Checkout
```
Title: Shopping Cart and Checkout Process
Requirement:
"Test complete purchase flow:
1. Search for products
2. Add products to cart
3. Apply coupon/discount codes
4. Select shipping method
5. Choose payment method
6. Review order summary
7. Place order
8. Receive order confirmation email

Test error scenarios:
- Invalid coupon codes
- Expired discounts
- Unavailable shipping
- Payment gateway errors
- Out of stock handling"

URL: https://demo.opencart.com
Module: Checkout System
```

---

### 3. **Magento Demo Store**

**URL:** https://magento2-demo.magebit.com

**Key Features:**
- Enterprise e-commerce
- Advanced product catalog
- Layered navigation
- Multiple warehouses
- Complex checkout

**Test Scenarios:**

#### Scenario 1: Advanced Product Filtering
```
Title: Complex Product Discovery
Requirement:
"Test advanced filtering capabilities:
1. Use layered navigation (color, size, brand)
2. Apply multiple simultaneous filters
3. Sort by popularity, rating, price
4. View product details with images
5. Read customer reviews
6. Check stock availability
7. Compare multiple products
8. Add to cart with options

Validate:
- Filter combinations
- Price range accuracy
- Stock status indicators
- Image loading
- Review authenticity
- Comparison accuracy"

URL: https://magento2-demo.magebit.com
Module: Product Catalog
```

---

### 4. **WordPress Test Site** (Content Management)

**URL:** https://wordpress.org/demo

**Key Features:**
- Blog posts
- Comments system
- Categories/Tags
- Search functionality
- User authentication
- Media uploads

**Test Scenarios:**

#### Scenario 1: Blog Navigation and Interaction
```
Title: Content Browsing and Commenting
Requirement:
"Test content management system:
1. Navigate blog posts
2. Filter by category/tag
3. Search for content
4. Read full articles
5. Post comments (if allowed)
6. Rate content
7. Share on social media
8. Subscribe to newsletter

Validate:
- Content rendering
- Comment moderation
- Search accuracy
- Social sharing links
- Email subscription
- Media loading"

URL: https://wordpress.org/demo
Module: Content Management
```

---

### 5. **GitHub Pages Test Site** (Issue Tracker)

**URL:** https://github.com/features/issues

**Key Features:**
- Issue creation/management
- Pull requests
- Code review
- Collaboration features

**Test Scenarios:**

#### Scenario 1: Issue Management
```
Title: GitHub Issues Workflow
Requirement:
"Test issue tracking system:
1. Create new issue
2. Add labels and assignees
3. Set priority and milestones
4. Add comments and attachments
5. Link related issues
6. Create pull request for fix
7. Review code changes
8. Merge to main branch

Validate:
- Issue template validation
- Label auto-complete
- Mention notifications
- PR linking
- Merge conflicts
- Review workflow"

URL: https://github.com
Module: Issue Tracking
```

---

### 6. **Trello Demo Board** (Project Management)

**URL:** https://trello.com/b/JEVJZ0Vm/welcome-board

**Key Features:**
- Kanban boards
- Card management
- Drag-and-drop
- Comments
- Attachments
- Labels

**Test Scenarios:**

#### Scenario 1: Project Board Interactions
```
Title: Kanban Board Management
Requirement:
"Test project management board:
1. Create new cards
2. Organize cards in lists
3. Drag cards between lists
4. Add checklists to cards
5. Assign team members
6. Set due dates
7. Add labels and priorities
8. Comment on cards
9. Attach files
10. Archive completed tasks

Edge cases:
- Drag large number of cards
- Nested checklists
- Member permission changes
- Date validation
- File size limits"

URL: https://trello.com
Module: Task Management
```

---

### 7. **GitLab Demo** (DevOps Platform)

**URL:** https://gitlab.com/explore/projects

**Key Features:**
- Repository browsing
- CI/CD pipelines
- Issue tracking
- Merge requests
- Wikis

**Test Scenarios:**

#### Scenario 1: Repository Management
```
Title: GitLab Project Workflow
Requirement:
"Test complete DevOps workflow:
1. Browse public repositories
2. View project details
3. Check CI/CD pipeline status
4. Review recent commits
5. View branches and tags
6. Access project wiki
7. Check issues and merge requests
8. View project analytics

Validate:
- Page load performance
- Pipeline status accuracy
- Commit information display
- Branch listing
- Issue pagination
- Search functionality"

URL: https://gitlab.com
Module: DevOps Platform
```

---

### 8. **Google Forms Demo**

**URL:** https://docs.google.com/forms/d/e/1FAIpQLSc1dLPy6z-rYOAKL0K-h0qEWu1aWJO1z1ZZPVN5EBCwGLaEKw/viewform

**Key Features:**
- Form fields validation
- Multiple choice options
- File uploads
- Conditional logic
- Auto-save
- Responses tracking

**Test Scenarios:**

#### Scenario 1: Form Submission and Validation
```
Title: Survey Form Completion
Requirement:
"Test form submission workflow:
1. Fill out text inputs
2. Select from dropdowns
3. Choose radio buttons
4. Check required fields
5. Upload files/images
6. Preview form
7. Submit form
8. Verify confirmation message
9. Access form responses (if accessible)

Include validation tests for:
- Required field messages
- Format validation (email, phone)
- File type/size restrictions
- Maximum character limits
- Date range validation"

URL: https://docs.google.com/forms
Module: Form Management
```

---

### 9. **Mailchimp Landing Page**

**URL:** https://mailchimp.com

**Key Features:**
- Email newsletter signup
- Feature showcase
- Pricing information
- Call-to-action buttons
- Form validation

**Test Scenarios:**

#### Scenario 1: Newsletter Signup
```
Title: Email Newsletter Registration
Requirement:
"Test email marketing platform interface:
1. Navigate homepage
2. Find newsletter signup form
3. Enter email address
4. Validate email format
5. Submit signup
6. Verify confirmation message
7. Check for follow-up options
8. Test error handling for invalid emails

Validate:
- Email format validation
- Duplicate email handling
- Loading states
- Success/error messages
- Accessibility
- Mobile responsiveness"

URL: https://mailchimp.com
Module: Email Marketing
```

---

### 10. **Booking.com Lite** (Travel)

**URL:** https://www.booking.com

**Key Features:**
- Search functionality
- Date pickers
- Property filtering
- Reviews and ratings
- Booking process
- Payment handling

**Test Scenarios:**

#### Scenario 1: Hotel Search and Booking
```
Title: Travel Booking Flow
Requirement:
"Test hotel booking platform:
1. Search hotels in location
2. Select check-in/check-out dates
3. Filter by price, rating, amenities
4. View property details
5. Check availability
6. Read guest reviews
7. Initiate booking
8. Fill booking details
9. Review total price with taxes/fees
10. Complete payment

Edge cases:
- Search with no results
- Unavailable date ranges
- Price changes during booking
- Payment method validation
- Special requests handling
- Cancellation policies"

URL: https://www.booking.com
Module: Booking System
```

---

## 🎯 QUICK TEST TEMPLATES

### Template 1: E-Commerce Platform

```
Title: [Store Name] Complete Shopping Experience
Requirement:
"As an end customer, I want to:
1. Browse the product catalog
2. Search for specific items
3. Filter products by category/price
4. Add items to shopping cart
5. Review cart contents
6. Proceed to checkout
7. Provide shipping information
8. Select payment method
9. Review order summary
10. Confirm and place order
11. Receive order confirmation

System should:
- Validate all form inputs
- Handle out-of-stock items
- Calculate taxes correctly
- Process payments securely
- Send confirmation emails
- Handle payment failures gracefully"

URL: [Website URL]
Module: E-Commerce
```

### Template 2: Content Management System

```
Title: [Site Name] Content Discovery and Engagement
Requirement:
"Users should be able to:
1. Navigate content sections
2. Search for articles
3. Filter by category/date
4. Read full content
5. Post comments
6. Rate content
7. Share on social media
8. Subscribe to updates

Content platform should:
- Display content correctly
- Manage comments properly
- Handle high traffic
- Load media efficiently
- Validate comment content
- Send notifications"

URL: [Website URL]
Module: CMS
```

### Template 3: User Authentication

```
Title: [Platform Name] User Account Management
Requirement:
"Users need to:
1. Create new account
2. Verify email address
3. Login to account
4. Reset forgotten password
5. Update profile information
6. Change password
7. Enable two-factor authentication
8. Manage linked devices
9. View login history
10. Logout from all devices

Security requirements:
- Password strength validation
- Session timeout
- Invalid attempt limits
- Email verification
- 2FA support
- Password reset security"

URL: [Website URL]
Module: Authentication
```

---

## 📊 TEST MATRIX

| Site | Type | Complexity | Duration | Best For |
|------|------|-----------|----------|----------|
| Swag Labs | E-Commerce | Medium | 60-100s | Shopping flow |
| OpenCart | E-Commerce | High | 80-120s | Full checkout |
| Magento | E-Commerce | High | 100-150s | Complex filtering |
| WordPress | CMS | Low | 40-60s | Content browsing |
| GitHub | DevOps | High | 80-120s | Issue tracking |
| Trello | Project Mgmt | Medium | 60-90s | Drag-drop UI |
| GitLab | DevOps | High | 100-150s | CI/CD workflow |
| Google Forms | Forms | Low | 30-50s | Form validation |
| Mailchimp | Marketing | Low | 30-50s | Email signup |
| Booking | Travel | High | 100-150s | Complex booking |

---

## 🚀 HOW TO TEST WITH AGENTQE

### Step 1: Login to AgentQE
```
1. Go to http://localhost:3000
2. Login with credentials
3. Click "AgentQE ML" in sidebar
```

### Step 2: Fill Test Form
```
Title: [Give it a name]
Requirement: [Paste scenario from above]
URL: [Website URL]
Module: [Component being tested]
Max Cycles: 3
```

### Step 3: Run Pipeline
```
1. Click "Run AgentQE Pipeline"
2. Watch 14 stages execute
3. Wait 60-100 seconds
```

### Step 4: Review Results
```
Tabs to check:
- Overview: Feature intent
- Test Cases: Generated tests
- Browser Actions: Execution logs
- Auto-Heal: Healing events
- Final Report: Verdict
```

---

## 💡 RECOMMENDED STARTING POINTS

### For Beginners
**Start with:** Swag Labs (Sauce Demo)
- Simple interface
- Clear workflows
- Good for learning
- ~60 seconds execution

**Test Scenario:**
```
Title: Basic Shopping Test
Requirement:
"Test user can:
1. Login successfully
2. View products
3. Add item to cart
4. View cart
5. Logout"

URL: https://www.saucedemo.com
Module: Storefront
```

### For Intermediate Users
**Start with:** OpenCart Demo
- More features
- Realistic scenarios
- Complex interactions
- ~80 seconds execution

**Test Scenario:**
```
Title: Product Filtering Test
Requirement:
"Test product discovery:
1. Search for product
2. Apply category filter
3. Sort by price
4. Add to cart
5. View cart with product details"

URL: https://demo.opencart.com
Module: Product Catalog
```

### For Advanced Users
**Start with:** Magento Demo or GitHub
- Enterprise features
- Complex workflows
- Performance testing
- ~100+ seconds execution

**Test Scenario:**
```
Title: Advanced E-Commerce Workflow
Requirement:
"Test complete enterprise checkout:
1. Multi-level product filtering
2. Related products display
3. Cart price updates
4. Shipping calculations
5. Tax computation
6. Payment processing
7. Order confirmation email"

URL: https://magento2-demo.magebit.com
Module: Enterprise Commerce
```

---

## ⚙️ TIPS FOR BEST RESULTS

### 1. **Choose Right URL**
- Use HTTPS URLs
- Avoid sites that block automation
- Test public features (no login-walls)
- Ensure stable infrastructure

### 2. **Write Clear Requirements**
- Specific user actions
- Edge cases included
- Validation criteria clear
- Include error scenarios

### 3. **Set Realistic Expectations**
- AgentQE learns from selectors on live pages
- Self-healing handles UI changes
- ML ranking is experimental (untrained)
- Results improve with clear requirements

### 4. **Monitor Execution**
- Check "Browser Actions" for real-time logs
- Note healing events in "Auto-Heal" tab
- Review high-risk areas in report
- Check recommendations

### 5. **Iterate and Improve**
- Run multiple tests
- Refine requirements based on results
- Adjust complexity for better results
- Share findings with team

---

## ❌ SITES TO AVOID

**Avoid testing with:**
- Payment sites requiring real transactions
- Restricted access areas
- Sites that block automation/headless browsers
- Single-page applications without proper selectors
- Slow or unreliable infrastructure
- Sites with complex authentication (CAPTCHA, 2FA)

---

## 📝 SAMPLE TEST RUN

### Example: Testing Swag Labs

**Setup:**
```
Title: Sauce Labs Shopping Cart Test
Requirement:
"Test complete shopping workflow:
1. User logs in with standard_user / secret_sauce
2. Browse product inventory
3. Add 'Sauce Labs Backpack' to cart
4. Add 'Test.allTheThings() T-Shirt' to cart
5. Verify items in cart
6. Proceed to checkout
7. Fill in shipping details:
   - First Name: John
   - Last Name: Doe
   - Zip Code: 12345
8. Continue to review
9. Verify total price
10. Complete purchase

The system should:
- Show correct product images
- Calculate prices accurately
- Validate shipping address
- Display order confirmation
- Show order number"

URL: https://www.saucedemo.com
Module: E-Commerce
Max Cycles: 3
```

**Expected Results:**
- 15-20 test cases generated
- ~90 seconds execution
- 80-95% pass rate
- 1-2 auto-healed tests
- Clear deployment verdict

---

## 📞 GETTING HELP

**For issues:**
1. Check "Browser Actions" tab for execution logs
2. Review "Auto-Heal" statistics
3. Check final report for recommendations
4. Verify URL is accessible
5. Check requirement clarity

**Common issues:**
- CORS blocking automation → Use HTTPS, avoid blocked sites
- No selectors found → Site might have dynamic DOM
- Timeouts → Site too slow, try different one
- Payment blocks → Avoid payment sites
- 404s → Check URL accuracy

---

## 🎓 LEARNING OUTCOMES

After testing with AgentQE, you'll understand:

✅ How multi-agent orchestration works  
✅ How ML ranking prioritizes tests  
✅ How self-healing recovers from failures  
✅ How risk analysis evaluates deployment readiness  
✅ How real-world testing scenarios work  
✅ How to interpret test reports  
✅ How to improve test generation  

---

**Ready to Test?**

Pick a site, write a requirement, and run your first AgentQE test!

👉 **Start with:** https://www.saucedemo.com

---

**Last Updated:** 2026-09-25  
**Status:** ✅ READY TO USE
