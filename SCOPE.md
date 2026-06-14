# SCOPE.md
## Anomaly Log

Below is the list of data problems systematically handled by the `import_expenses` pipeline, mapping directly back to the project requirements:

### Identified Anomalies & Policies Handled
1. **Duplicate Entries**: (Meera's Request). Handled by tracking uniqueness hashes per row based on specific identifiers (date + description + amount) and alerting users before import.
2. **Settlements logged as Expenses**: Detected by reading either negative balances, description keywords (like "Settled", "Paid back"), and dynamically casting these into the `Settlements` table rather than parsing into `Expense / ExpenseSplit`.
3. **Currency Discrepancies**: (Priya's Request). Checked via string formats (`$` vs `₹`). Logged in DB properly using the `currency` string attribute. A USD/INR conversion rate must be applied logically on balances calculation or globally adjusted.
4. **Member Residency Conflicts**: (Sam & Meera's Request). Validated by checking the `Expense` date against `GroupMember`'s `joined_at` and `left_at` fields globally before mapping `.splits`. If a user was not active, they are skipped/ignored natively.
5. **Inconsistent Date Format**: Resolved utilizing an aggressive string interpolation try/except catch cycle `parse_date()`.
6. **Inconsistent Number Format**: Cleaning out comma-separated values, negative formats natively into Python `Decimal` to avoid float calculation drifts.

## Database Schema
- **User**: `id`, `username`, `email`, `password_hash`
- **Group**: `id`, `name`, `description`, `created_at`
- **GroupMember**: `id`, `user_id`, `group_id`, `joined_at`, `left_at`
- **Expense**: `id`, `group_id`, `paid_by_id`, `description`, `amount`, `currency`, `date`, `split_type`
- **ExpenseSplit**: `id`, `expense_id`, `user_id`, `amount`
- **Settlement**: `id`, `group_id`, `payer_id`, `payee_id`, `amount`, `date`
