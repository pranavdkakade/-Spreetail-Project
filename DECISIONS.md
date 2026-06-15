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
- **Why:** The core document explicitly noted a "settlement logged as an expense" mapped as an anomaly. To prevent debts multiplying exponentially instead of calculating correctly, parsing transactions globally mapping "payments resolving debts" vs "new debts owed" ensures complete analytical stability. Doing so cleanly answers Aisha's request for single distinct values resolving debts.

### 4. Direct Mapped Split Amounts
- **Decision:** Mapping `ExpenseSplit` natively recording hard `amount` decimals instead of global percentage weights.
- **Why:** Directly addresses Rohan's request ("No magic numbers"). When queried, a user profile iterates exclusively its own `ExpenseSplit` objects linked historically back to main `Expense` records, ensuring mathematical traceabilities are 1-1 precise, without rounding-error ghosts.

### 5. Monetary Parsing & Types
- **Decision:** Storing amounts as `DECIMAL(10,2)` via `Numeric` vs python floats globally.
- **Why:** Floats inherit drifting trailing decimals causing fraction disparities at large scales (e.g., $100 / 3). Implementing exact precision types across the database protects calculations natively.

### 6. Interactive CSV Approval Interface
- **Decision:** Build an interactive preview approval screen in the browser rather than a command line utility or a silent guess.
- **Why:** Fully satisfies Meera's request ("Clean up duplicates — but I want to approve anything the app deletes or changes"). It places the user in control, surfacing warnings, letting them choose which duplicates to drop, and validating corrections transparently before committing to the database.

### 7. USD Conversion Rate Description Annotation
- **Decision:** Append original USD currencies and exchange rates directly to the expense description fields (e.g. `(USD 540.00 @ 83.00)`) during import instead of creating separate tables/columns.
- **Why:** Allows Priya and the roommates to trace USD conversion rates transparently on all dashboards (ledger, group view, lists) without violating existing SQL schema migrations.

### 8. Dynamic HTTP POST splits over dynamic WTForms
- **Decision:** Parse form POST data for split calculations directly in the controller instead of trying to map WTForms fields.
- **Why:** Manual expense entry splits are dynamic (e.g. split values change whether it is EQUAL, PERCENTAGE, UNEQUAL, or SHARE, and change based on active members). Standard form parsing provides maximum flexibility, allowing clean Javascript toggles and precise backend validation of percentage sums.
