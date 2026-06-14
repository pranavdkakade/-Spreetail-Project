import csv
from datetime import datetime
import os
from decimal import Decimal

# Helper functions for the data importer

def parse_date(date_str):
    # Depending on what the CSV looks like, we might need multiple formats
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%d-%b-%y'):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Time data '{date_str}' does not match any known format")

def clean_amount(amount_str):
    if not amount_str:
        return Decimal('0.00')
    # Strip symbols
    clean_str = str(amount_str).replace('$', '').replace('₹', '').replace(',', '').strip()
    try:
        return Decimal(clean_str)
    except Exception:
        return None

def detect_currency(amount_str):
    if '$' in str(amount_str):
        return 'USD'
    return 'INR'

def generate_import_report(anomalies):
    report_path = os.path.join(os.getcwd(), 'import_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("Expense Import Report\n")
        f.write("=====================\n\n")
        for anomaly in anomalies:
            f.write(f"- {anomaly}\n")
    return report_path