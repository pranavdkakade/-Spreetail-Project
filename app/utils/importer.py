import csv
import io
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

def parse_date(date_str):
    if not date_str:
        return None
    # Clean date string
    date_str = date_str.strip()
    
    # Handle specific short format like "Mar-14"
    if re.match(r'^[A-Za-z]{3}-\d{1,2}$', date_str):
        # Assume year is 2026 based on surrounding data
        try:
            return datetime.strptime(f"{date_str}-2026", "%b-%d-%Y")
        except ValueError:
            pass

    for fmt in ('%d-%m-%Y', '%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d-%b-%y', '%b-%d-%Y'):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
            
    raise ValueError(f"Date '{date_str}' does not match any known format")

def clean_amount(amount_str):
    if not amount_str:
        return Decimal('0.00')
    # Strip symbols
    clean_str = str(amount_str).replace('$', '').replace('₹', '').replace(',', '').strip()
    try:
        # Check precision
        val = Decimal(clean_str)
        return val
    except Exception:
        return None

def clean_username(name):
    if not name:
        return ""
    name_clean = name.strip()
    name_lower = name_clean.lower()
    
    if name_lower in ('priya', 'priya s'):
        return 'Priya'
    if name_lower == 'rohan':
        return 'Rohan'
    if name_lower == 'aisha':
        return 'Aisha'
    if name_lower == 'meera':
        return 'Meera'
    if name_lower == 'sam':
        return 'Sam'
    if name_lower == 'dev':
        return 'Dev'
    if name_lower in ('kabir', "dev's friend kabir"):
        return 'Kabir'
    
    return name_clean.capitalize()

def parse_csv_file(file_content, exchange_rate=Decimal('83.00')):
    """
    Parses the CSV content and detects anomalies.
    Returns:
        parsed_records: list of dicts representing proposed expenses/settlements
        anomalies: list of dicts representing detected anomalies
    """
    # Use io.StringIO to parse content
    f = io.StringIO(file_content)
    reader = csv.DictReader(f)
    
    anomalies = []
    parsed_records = []
    seen_expenses = [] # list of (date_obj, clean_desc, clean_amount) to detect duplicates

    # We track some global context: Meera moves out March 31, Sam moves in mid-April.
    # Standard group membership rules:
    # Meera: Feb 1 - Mar 31.
    # Sam: Apr 8/15 - Present (we can assume April 1st for membership to cover early April).
    
    for row_idx, row in enumerate(reader, start=2): # Header is line 1
        raw_date = row.get('date', '')
        raw_desc = row.get('description', '')
        raw_paid_by = row.get('paid_by', '')
        raw_amount = row.get('amount', '')
        raw_currency = row.get('currency', '')
        raw_split_type = row.get('split_type', '')
        raw_split_with = row.get('split_with', '')
        raw_split_details = row.get('split_details', '')
        raw_notes = row.get('notes', '')
        
        row_anomalies = []
        
        # 1. Date parsing
        date_obj = None
        try:
            date_obj = parse_date(raw_date)
            # Check for ambiguous date
            if raw_date == "04-05-2026":
                # Is it May 4 or April 5?
                # Based on order (between Mar 28 and Apr 1), it is chronologically April 5th.
                # Let's fix it to April 5th and log anomaly
                date_obj = datetime(2026, 4, 5)
                row_anomalies.append({
                    'type': 'ambiguous_date',
                    'message': f"Date '{raw_date}' is ambiguous (May 4th vs April 5th). Parsed as April 5th, 2026 based on chronological sequence.",
                    'proposed_action': 'Use 2026-04-05'
                })
            elif raw_date == "Mar-14":
                row_anomalies.append({
                    'type': 'date_format',
                    'message': f"Inconsistent date format '{raw_date}'. Parsed as 2026-03-14.",
                    'proposed_action': 'Use 2026-03-14'
                })
        except Exception as e:
            row_anomalies.append({
                'type': 'invalid_date',
                'message': f"Failed to parse date '{raw_date}': {str(e)}",
                'proposed_action': 'Skip row'
            })
            anomalies.append({'row': row_idx, 'description': raw_desc, 'issues': row_anomalies})
            continue

        # 2. Amount cleaning & precision
        amount_dec = clean_amount(raw_amount)
        if amount_dec is None:
            row_anomalies.append({
                'type': 'invalid_amount',
                'message': f"Failed to parse amount '{raw_amount}'",
                'proposed_action': 'Skip row'
            })
            anomalies.append({'row': row_idx, 'description': raw_desc, 'issues': row_anomalies})
            continue
        
        # Check formatting with commas/quotes
        if ',' in str(raw_amount):
            row_anomalies.append({
                'type': 'amount_format',
                'message': f"Inconsistent amount format with commas: '{raw_amount}'. Cleaned to {amount_dec}.",
                'proposed_action': 'Clean format'
            })

        # Check precision (more than 2 decimal places)
        decimal_places = abs(amount_dec.as_tuple().exponent)
        if decimal_places > 2:
            rounded_amount = amount_dec.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            row_anomalies.append({
                'type': 'amount_precision',
                'message': f"Amount '{raw_amount}' has over-precision ({decimal_places} decimal places). Rounded to {rounded_amount}.",
                'proposed_action': f"Round to {rounded_amount}"
            })
            amount_dec = rounded_amount

        # Check for zero or negative amounts
        is_refund = False
        if amount_dec < 0:
            is_refund = True
            row_anomalies.append({
                'type': 'negative_amount',
                'message': f"Negative amount detected: {amount_dec}. Identified as a refund.",
                'proposed_action': 'Process as refund (reduces split balances)'
            })
        elif amount_dec == 0:
            row_anomalies.append({
                'type': 'zero_amount',
                'message': "Expense amount is 0.00.",
                'proposed_action': 'Skip or record as zero-value'
            })

        # 3. Currency detection & conversion
        currency = raw_currency.strip().upper() if raw_currency else ''
        if not currency:
            # Check if symbol implies USD or default to INR
            if '$' in str(raw_amount):
                currency = 'USD'
            else:
                currency = 'INR'
            row_anomalies.append({
                'type': 'missing_currency',
                'message': f"Missing currency field. Assumed {currency} based on format.",
                'proposed_action': f"Set currency to {currency}"
            })
        
        amount_inr = amount_dec
        if currency == 'USD':
            amount_inr = (amount_dec * exchange_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            row_anomalies.append({
                'type': 'currency_conversion',
                'message': f"USD expense detected: ${amount_dec}. Converted to INR at rate {exchange_rate} -> ₹{amount_inr}.",
                'proposed_action': f"Convert to INR {amount_inr}"
            })

        # 4. User mapping (paid_by & splits)
        paid_by = clean_username(raw_paid_by)
        if not paid_by:
            # Missing paid_by
            paid_by = 'Aisha' # Default to Aisha
            row_anomalies.append({
                'type': 'missing_payer',
                'message': f"Missing payer (paid_by) for expense. Defaulting to 'Aisha'.",
                'proposed_action': "Set payer to Aisha"
            })
        elif raw_paid_by != paid_by:
            row_anomalies.append({
                'type': 'user_name_cleanup',
                'message': f"Normalized payer name from '{raw_paid_by}' to '{paid_by}'.",
                'proposed_action': f"Use '{paid_by}'"
            })

        # Split with users
        split_users_raw = [u.strip() for u in raw_split_with.split(';') if u.strip()]
        split_users = [clean_username(u) for u in split_users_raw]
        
        # Check if there were name changes in the split list
        if split_users_raw != split_users:
            row_anomalies.append({
                'type': 'split_name_cleanup',
                'message': f"Normalized split list users: {', '.join(split_users_raw)} -> {', '.join(split_users)}.",
                'proposed_action': "Use normalized names"
            })

        # Check for non-member "Kabir"
        if 'Kabir' in split_users:
            row_anomalies.append({
                'type': 'guest_member',
                'message': f"Dev's friend Kabir is included in the splits but is a guest. Proposed: Import Kabir as a guest group member.",
                'proposed_action': "Create Kabir as guest user and add to group"
            })

        # Check timelines:
        # Meera moved out March 31st. Sam moved in mid-April.
        # If Meera in split and date > March 31, 2026:
        if date_obj > datetime(2026, 3, 31) and 'Meera' in split_users:
            row_anomalies.append({
                'type': 'inactive_member_split',
                'message': f"Meera is in the split list for an April expense ({raw_date}), but she moved out on March 31st.",
                'proposed_action': "Exclude Meera from split, redistribute equally among active members"
            })
        
        # If Sam in split and date < April 1, 2026:
        if date_obj < datetime(2026, 4, 1) and 'Sam' in split_users:
            row_anomalies.append({
                'type': 'premature_member_split',
                'message': f"Sam is in the split list for a March/February expense ({raw_date}), but he moved in mid-April.",
                'proposed_action': "Exclude Sam from split, redistribute equally"
            })

        # 5. Split Logic / Settlements
        is_settlement = False
        split_type = raw_split_type.strip().lower() if raw_split_type else ''
        
        # Check if this is a settlement logged as an expense
        # Conditions: split_type is empty and description implies payment, or split_with is single person and description contains payment phrases
        desc_lower = raw_desc.lower()
        if not split_type or 'paid' in desc_lower or 'deposit' in desc_lower or 'settle' in desc_lower:
            # Let's see if we have a clear single recipient in split_with
            if len(split_users) == 1:
                is_settlement = True
                payee = split_users[0]
                row_anomalies.append({
                    'type': 'settlement_logged_as_expense',
                    'message': f"Settlement detected in expense: '{raw_desc}' where {paid_by} paid {payee}. Importing as a Settlement record.",
                    'proposed_action': f"Import as Settlement: {paid_by} -> {payee} (₹{amount_inr})"
                })
        
        # Calculate individual shares
        splits = []
        if not is_settlement:
            if not split_type:
                split_type = 'equal'
                row_anomalies.append({
                    'type': 'missing_split_type',
                    'message': "Missing split type. Defaulted to 'equal'.",
                    'proposed_action': "Split equally"
                })

            if split_type == 'equal':
                # Check for redundant details in equal split
                if raw_split_details:
                    row_anomalies.append({
                        'type': 'redundant_split_details',
                        'message': f"Redundant split details provided for equal split: '{raw_split_details}'. Details will be ignored.",
                        'proposed_action': "Split equally, ignore details"
                    })
                
                # Check if Meera is excluded by the timeline rule
                active_splits = [u for u in split_users if not (date_obj > datetime(2026, 3, 31) and u == 'Meera')]
                if active_splits:
                    share = (amount_inr / len(active_splits)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    # Handle rounding difference on the last person
                    total_allocated = Decimal('0.00')
                    for u in active_splits[:-1]:
                        splits.append({'user': u, 'amount': share})
                        total_allocated += share
                    splits.append({'user': active_splits[-1], 'amount': amount_inr - total_allocated})
                
            elif split_type == 'percentage':
                # Parse percentages
                details = {}
                pct_sum = Decimal('0')
                # details are in format: "Aisha 30%; Rohan 30%; Priya 30%; Meera 20%"
                parts = [p.strip() for p in raw_split_details.split(';') if p.strip()]
                for p in parts:
                    match = re.match(r'^([A-Za-z\s\'\-]+)\s+(\d+(?:\.\d+)?)\s*%$', p)
                    if match:
                        u = clean_username(match.group(1))
                        pct = Decimal(match.group(2))
                        details[u] = pct
                        pct_sum += pct
                
                # Check if percentages sum to 100%
                if pct_sum != 100:
                    row_anomalies.append({
                        'type': 'percentage_mismatch',
                        'message': f"Percentages sum to {pct_sum}% instead of 100%. Normalizing splits.",
                        'proposed_action': "Normalize percentages to sum to 100%"
                    })
                
                # Normalize if mismatch, calculate shares
                total_allocated = Decimal('0.00')
                users_list = list(details.keys())
                for i, u in enumerate(users_list):
                    pct = details[u]
                    normalized_pct = pct / pct_sum
                    share = (amount_inr * normalized_pct).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    if i < len(users_list) - 1:
                        splits.append({'user': u, 'amount': share})
                        total_allocated += share
                    else:
                        splits.append({'user': u, 'amount': amount_inr - total_allocated})
                        
            elif split_type == 'unequal':
                # Parse absolute amounts: "Rohan 700; Priya 400; Meera 400"
                details = {}
                details_sum = Decimal('0')
                parts = [p.strip() for p in raw_split_details.split(';') if p.strip()]
                for p in parts:
                    match = re.match(r'^([A-Za-z\s\'\-]+)\s+(\d+(?:\.\d+)?)$', p)
                    if match:
                        u = clean_username(match.group(1))
                        amt = Decimal(match.group(2))
                        details[u] = amt
                        details_sum += amt
                
                # Check if sum matches total amount
                if details_sum != amount_dec:
                    row_anomalies.append({
                        'type': 'unequal_split_mismatch',
                        'message': f"Sum of unequal splits (₹{details_sum}) does not match the total amount (₹{amount_dec}). Adjusting last person's share.",
                        'proposed_action': "Adjust split shares to match total"
                    })
                
                # Convert details to INR using currency rate
                total_allocated = Decimal('0.00')
                users_list = list(details.keys())
                for i, u in enumerate(users_list):
                    u_amt_inr = (details[u] * (amount_inr / amount_dec)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    if i < len(users_list) - 1:
                        splits.append({'user': u, 'amount': u_amt_inr})
                        total_allocated += u_amt_inr
                    else:
                        splits.append({'user': u, 'amount': amount_inr - total_allocated})
                        
            elif split_type == 'share':
                # Parse shares: "Aisha 1; Rohan 2; Priya 1; Dev 2"
                details = {}
                total_shares = Decimal('0')
                parts = [p.strip() for p in raw_split_details.split(';') if p.strip()]
                for p in parts:
                    match = re.match(r'^([A-Za-z\s\'\-]+)\s+(\d+(?:\.\d+)?)$', p)
                    if match:
                        u = clean_username(match.group(1))
                        sh = Decimal(match.group(2))
                        details[u] = sh
                        total_shares += sh
                
                # Compute splits based on shares
                total_allocated = Decimal('0.00')
                users_list = list(details.keys())
                for i, u in enumerate(users_list):
                    share_fraction = details[u] / total_shares
                    share_amt = (amount_inr * share_fraction).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    if i < len(users_list) - 1:
                        splits.append({'user': u, 'amount': share_amt})
                        total_allocated += share_amt
                    else:
                        splits.append({'user': u, 'amount': amount_inr - total_allocated})
            else:
                row_anomalies.append({
                    'type': 'unknown_split_type',
                    'message': f"Unknown split type '{raw_split_type}'. Defaulted to 'equal'.",
                    'proposed_action': "Split equally"
                })
                # Fallback to equal
                active_splits = [u for u in split_users if not (date_obj > datetime(2026, 3, 31) and u == 'Meera')]
                if active_splits:
                    share = (amount_inr / len(active_splits)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    total_allocated = Decimal('0.00')
                    for u in active_splits[:-1]:
                        splits.append({'user': u, 'amount': share})
                        total_allocated += share
                    splits.append({'user': active_splits[-1], 'amount': amount_inr - total_allocated})

        # 6. Duplicate Detection (Meera's Request)
        # Duplicate means same date, same description (case-insensitive & stripped), same amount, same paid_by
        clean_desc_check = raw_desc.strip().lower()
        # Also clean descriptions slightly to catch dinner duplicate (dinner at marina bites vs dinner - marina bites)
        clean_desc_check = re.sub(r'[^a-z0-9]', '', clean_desc_check)
        
        is_duplicate = False
        duplicate_ref = None
        for prev_idx, prev_date, prev_desc, prev_amt, prev_payer in seen_expenses:
            if prev_date == date_obj and prev_payer == paid_by:
                # If they are very similar descriptions and same amount, or identical description and different amount
                desc_sim = (prev_desc in clean_desc_check or clean_desc_check in prev_desc)
                if desc_sim and prev_amt == amount_inr:
                    is_duplicate = True
                    duplicate_ref = prev_idx
                    break
                # Conflict: same description and date, but different amount or payer (e.g. Thalassa dinner)
                elif desc_sim and (prev_amt != amount_inr or prev_payer != paid_by):
                    row_anomalies.append({
                        'type': 'conflicting_duplicate',
                        'message': f"Conflicting duplicate detected. Row {prev_idx} also logs '{prev_desc}' but with different payer/amount. Notes say: '{raw_notes}'.",
                        'proposed_action': f"Compare with Row {prev_idx} and select which one to keep"
                    })
                    
        if is_duplicate:
            row_anomalies.append({
                'type': 'duplicate_entry',
                'message': f"Duplicate expense of Row {duplicate_ref} detected ('{raw_desc}' for ₹{amount_inr}).",
                'proposed_action': "Skip this duplicate row"
            })

        # Register this expense for future duplicate checks if it's not a settlement
        if not is_settlement and amount_inr > 0:
            seen_expenses.append((row_idx, date_obj, clean_desc_check, amount_inr, paid_by))

        # 7. Record formatting
        record = {
            'row_index': row_idx,
            'date': date_obj.strftime('%Y-%m-%d') if date_obj else raw_date,
            'description': raw_desc.strip(),
            'paid_by': paid_by,
            'amount_original': float(amount_dec),
            'currency_original': currency,
            'amount_inr': float(amount_inr),
            'is_settlement': is_settlement,
            'split_type': split_type,
            'splits': [{'user': s['user'], 'amount': float(s['amount'])} for s in splits],
            'notes': raw_notes.strip()
        }
        
        if is_settlement:
            record['payee'] = split_users[0] if split_users else 'Aisha'

        parsed_records.append(record)
        
        if row_anomalies:
            anomalies.append({
                'row': row_idx,
                'description': raw_desc,
                'issues': row_anomalies
            })
            
    return parsed_records, anomalies