# DECISIONS.md

## Decision Log

### 1. Database Choice & Relational Management
- **Decision:** SQLite -> PostgreSQL (Ready). Utilizing SQLAlchemy as the ORM.
- **Why:** The instructions restrict us strictly to Relational Databases. Utilizing SQLAlchemy handles exact abstraction between rapid SQLite local prototypes and Render.com's strict PostgreSQL requirement via mere `.env` string replacements.

### 2. Group Memberships & Time-based Tracking
- **Decision:** Introduce `joined_at` and `left_at` columns gracefully tracking "historical" membership.
- **Why:** The instructions mentioned Sam moved in mid-April, and Meera moved out late-March. Without timestamp tracking tied directly to the member junction block (`GroupMember`), historical split maths would inherently fail resulting in calculating March expenses for someone who joined sequentially late.

### 3. Expense/Settlement Segregation
- **Decision:** Completely separate the tables of `Expense` and `Settlement`.
- **Why:** The core document explicitly noted a "settlement logged as an expense" mapped as an anomaly. To prevent debts multiplying exponentially instead of clearing logically, parsing transactions globally mapping "payments resolving debts" vs "new debts owed" ensures complete analytical stability. Doing so cleanly answers Aisha's request for single distinct values resolving debts seamlessly.

### 4. Direct Mapped Split Amounts
- **Decision:** Mapping `ExpenseSplit` natively recording hard `amount` decimals instead of global percentage weights.
- **Why:** Directly addresses Rohan's request ("No magic numbers"). When queried, a user profile iterates exclusively its own `ExpenseSplit` objects linked historically back to main `Expense` records, ensuring mathematical traceabilities are 1-1 precise, without rounding-error ghosts.

### 5. Monetary Parsing & Types
- **Decision:** Storing amounts as `DECIMAL(10,2)` via `Numeric` vs python floats globally.
- **Why:** Floats inherit drifting trailing decimals causing fraction disparities at large scales (e.g., $100 / 3). Implementing exact precision types across the database protects calculations natively.
