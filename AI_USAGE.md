# AI_USAGE.md

## AI Collaboration Log

This document outlines the usage of AI tools during the development of the Shared Expenses App, including the key prompts and concrete cases where AI code was corrected for accuracy.

### 1. AI Tools Used
- **AI Collaborator**: Gemini 3.5 Flash via Antigravity IDE (Google DeepMind Team).
- **Role**: Pair programmer and design advisor.

### 2. Key Prompts Used
- *"Build a production-ready Shared Expenses App using Flask, SQLAlchemy, PostgreSQL, Flask-Login, HTML, Bootstrap 5..."*
- *"Help me step by step to make as they have shown they do not need bulk commit on GitHub, so after every step tell me when to upload to GitHub..."*
- *"Implement the CSV parser in app/utils/importer.py to handle 18+ specific anomalies found in the CSV file..."*

---

### 3. Cases where the AI Code was Corrected

#### Case 1: Float Division Drift in Split Calculations
- **What the AI produced**: The AI suggested using python float division (`amount / len(members)`) to compute equal shares.
- **Why it was wrong**: Floating-point division inherits representation drift (e.g. `100.00 / 3` is `33.333333333333336`). In accounting, this creates fraction-of-a-cent errors, causing the sum of splits to mismatch the total expense amount.
- **How we caught it**: During a manual calculation check, the total split shares did not sum exactly to the parent expense amount.
- **What was changed**: We refactored the division to use Python `Decimal` library with `ROUND_HALF_UP` precision. Additionally, we implemented a remainder-matching loop where the final member absorbs the rounding difference (e.g. 33.33 + 33.33 + 33.34 = 100.00).

#### Case 2: Flask `BuildError` for Undefined Routing Links
- **What the AI produced**: The AI generated navigation buttons and ledger detail links in `view.html` pointing to endpoints (`add_expense`, `record_settlement`, `member_ledger`) before creating the endpoints in the controller.
- **Why it was wrong**: Running Flask at this intermediate commit would trigger a critical `BuildError` (unable to resolve endpoint URLs), crashing the development server.
- **How we caught it**: During step-by-step compilation, the server crashed due to missing routes in the Blueprint.
- **What was changed**: We introduced temporary controller stubs in `app/routes/group.py` immediately after drafting the template. This kept the app compiling and testing seamlessly through every single commit.

#### Case 3: Settlement cashflow double-counting
- **What the AI produced**: The AI initially treated settlements (like *"Rohan paid Aisha back"*) as standard group expenses, splitting it equally among members.
- **Why it was wrong**: Doing so meant Rohan was charged for paying Aisha back, which doubled the debt rather than clearing it.
- **How we caught it**: Tracing Rohan's balance by hand, we saw that instead of clearing his balance to zero, he ended up owing even more money.
- **What was changed**: We completely segregated the `Settlement` table from the `Expense` table, and corrected the balance calculation formula to:
  `Balance = PaidExpenses - SplitShares + SettlementsPaid - SettlementsReceived`
  This netted out cash handovers correctly.
