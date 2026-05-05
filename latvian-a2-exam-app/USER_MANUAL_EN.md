# Latvian A2 Exam Simulator (Codex) - User Manual

## Contents
1. [Quick Start (5 minutes)](#quick-start-5-minutes)
2. [Navigation Map](#navigation-map)
3. [Key Workflows](#key-workflows)
4. [Admin/Super User Section](#admin-super-user-section)
5. [Troubleshooting Guide](#troubleshooting-guide)
6. [Cheat Sheet](#cheat-sheet)

---

## Quick Start (5 minutes)

1. **Starting an Exam**
   - Open your web browser and go to `http://localhost:4173` (or your server address)
   - In the **Exam** section, select "A2 Mock Exam 01" from the dropdown
   - Click the **Submit Answers** button to start the exam simulation
   - Complete all tasks (listening, reading, writing, speaking)
   - When ready, click **Submit Answers** in the bottom-left corner

2. **Viewing Submissions**
   - After submission, navigate to the **Submission** section
   - View your answers and total points
   - To receive AI evaluation, click the **AI Score** button

3. **Viewing Results**
   - After AI evaluation, go to the **Quality** section
   - View points for each skill and overall result
   - Check if you passed (minimum 9/15 points required in each skill)

---

## Navigation Map

The main layout consists of a left panel (navigation) and central workspace (content).

### Left Panel (Buttons)
- **Dashboard** – View your statistics, recent attempts, and free status
- **Exams** – List of available exams (A2 Mock Exam 01, 02, etc.)
- **Admin** – User and system settings (super users only)
- **Runner** – Where you take the exam simulation (default view)
- **Submission** – View your submitted answers after an exam
- **Billing** – Check subscription, purchase additional access or AI credits
- **Markdown** – View exam source (.md file)
- **JSON** – View exam data (JSON format)
- **TTS** – Listen to text-to-speech conversion (for accommodations)
- **Prompts** – View images for speaking section
- **Quality** – AI evaluation results and feedback

### Central Workspace
Changes based on the selected button in the left panel. Displays forms, text, diagrams, or other elements.

---

## Key Workflows

### Start a New Exam Attempt
1. Click **Runner** in the left panel
2. In the **Exam** dropdown, select the desired exam (e.g., "A2 Mock Exam 01")
3. The **Source Markdown** field shows which file will be used
4. Click **Submit Answers** – starts the timer
5. Complete all sections (listening, reading, writing, speaking)
6. When ready, click **Submit Answers** in the bottom-left corner
7. After submission, go to **Submission** or **Quality** to view results

### Resume an Attempt
> Note: This simulator does not support saving incomplete attempts. If you leave, you must start over.
> To retake the same exam:
> 1. Select the same exam in the **Exam** dropdown
> 2. Click the **Reload** button – clears all entered data
> 3. Start a new attempt as described above

### Check Your Access Status (Entitlements)
1. Click **Billing** in the left panel
2. View the **Your Entitlements** block at the bottom
   - **Free attempts remaining** – free attempts available today
   - **Paid attempts remaining** – paid attempts in your subscription
   - **AI credits remaining** – available AI evaluation credits
   - **Subscription status** – plan type (Free, Pro, Enterprise, etc.) and expiration date
3. If you see **Frozen**, your account is blocked due to payment or credit issues

### Purchase Access (Single Exam, Exam Pack, Subscription, AI Scoring Credits)
1. Click **Billing** in the left panel
2. In the **Purchase options** section, select:
   - **Single Exam** – one-time access to a specific exam
   - **Exam Pack** – bundle of multiple exams (e.g., 5 exams)
   - **Subscription** – monthly plan (e.g., Pro plan with unlimited exams)
   - **AI Scoring Credits** – additional credits for AI evaluation (if your plan quota is insufficient)
3. Click the **Buy** button for your selected product
4. Follow Stripe payment instructions (enter card details or use alternative payment)
5. After successful payment, your entitlements update automatically

### Enable/Verify AI Scoring and Interpret Results
1. After submitting an exam (see "Start a New Exam Attempt" above)
2. Click **AI Score** in the left panel – if button not visible, it means you want AI evaluation
3. Check if you have sufficient AI credits:
   - If you see a message "AI credits remaining: 0", you need to purchase more credits or wait for daily quota renewal
4. After AI evaluation completes:
   - Go to the **Quality** section
   - View:
     - Total points (maximum 60)
     - Points per skill (listening, reading, writing, speaking) – each requires minimum 9/15
     - Detailed feedback for each task group (e.g., "Writing: Task 1 – well structured, but needs more precise vocabulary")
   - If all skills have minimum 9/15 points, you passed. Otherwise, see which skills need improvement

---

## Admin/Super User Section

### What "Full Access" Means
Super users (admins) should have:
- Unlimited exam attempts (free and paid)
- Unlimited AI evaluation credits
- Access to Admin panel (user management, system settings)
- Ability to view all users and their statistics
- Ability to cancel or modify any user's subscription

### How to Verify Your Role and Entitlements
1. Click **Admin** in the left panel
2. If you see **User Management** or **System Settings** sections, you are an admin
3. Alternatively, go to **Billing** → check **Subscription status** – if it shows "admin" or "unlimited", you have full access
4. If you don't see the Admin button or its sections are empty, contact the system administrator or check the database

### Troubleshooting Checklist When AI Scoring Shows "credits remaining: 0"
1. Check your subscription status:
   - **Billing** → **Subscription status** – are you on Free, Pro, Enterprise, or admin plan?
   - If on Free plan, you have a limit (e.g., 3 AI evaluations per day)
2. Check your daily usage statistics:
   - If you've used all daily AI credits, you must wait until tomorrow or purchase additional credits
3. Check for payment issues:
   - If you recently purchased credits but they don't appear, check your Stripe purchase history or contact support
4. If you're an admin and still see credit shortage:
   - Go to **Admin** → **System Settings** → **AI Scoring Limits** and verify your plan limits aren't set to 0
   - If you previously changed settings, reset to default or maximum values
5. If everything seems correct but the problem persists:
   - Refresh the page (Ctrl+F5 or Cmd+Shift+R)
   - Clear browser cache or try a different browser
   - If still problematic, contact technical support with detailed description and screenshot

---

## Troubleshooting Guide (symptoms → causes → fixes)

| Symptom                                      | Causes                                              | Solutions                                                                 |
|----------------------------------------------|-----------------------------------------------------|----------------------------------------------------------------------------|
| **free_exhausted**                           | Used all free attempts today (3 per day)            | Wait until tomorrow or upgrade subscription for additional attempts        |
| **Paid attempts remaining: 0**               | Used all paid attempts in your subscription         | Purchase additional exam pack or upgrade to subscription with more attempts |
| **AI credits remaining: 0**                  | Used all daily AI evaluation credits                | Wait until tomorrow, purchase additional AI credits, or review subscription plan |
| "You have used the free exam…" (You have used the free exam…) | Attempted to access an exam not available for free | Use one of your free attempts or switch to paid option (Single Exam, Exam Pack, Subscription) |

---

## Cheat Sheet

| Action                                 | Where to Find and What to Click                                                                 |
|----------------------------------------|-------------------------------------------------------------------------------------------------|
| Start a new exam                      | **Runner** → select exam → **Submit Answers** (start)                                           |
| Submit answers                        | In each section while filling out → bottom-left corner → **Submit Answers**                     |
| View submission                       | After submission → **Submission**                                                               |
| Get AI evaluation                     | After submission → **AI Score**                                                                 |
| View AI results                       | After AI evaluation → **Quality**                                                               |
| Check free attempts remaining         | **Billing** → **Free attempts remaining**                                                       |
| Check paid attempts remaining         | **Billing** → **Paid attempts remaining**                                                       |
| Check AI credits remaining            | **Billing** → **AI credits remaining**                                                          |
| Purchase single exam                  | **Billing** → **Purchase options** → **Single Exam** → **Buy**                                 |
| Purchase exam pack                    | **Billing** → **Purchase options** → **Exam Pack** → **Buy**                                   |
| Purchase subscription                 | **Billing** → **Purchase options** → **Subscription** → **Buy**                                |
| Purchase additional AI credits        | **Billing** → **Purchase options** → **AI Scoring Credits** → **Buy**                          |
| Go to admin panel                     | **Admin** (only if you are a super user)                                                        |
| Reload exam (if error)                | Left panel → **Reload**                                                                         |
| Copy submission text                  | After submission → **Submission** → **Copy Submission**                                         |
| Download submission                   | After submission → **Submission** → **Download Submission** (or .md/.json)                     |