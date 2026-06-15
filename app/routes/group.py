from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from datetime import datetime, timezone
import os
from decimal import Decimal
from app import db, bcrypt
from app.models.group import Group, GroupMember
from app.models.user import User
from app.forms import GroupForm, AddMemberForm
from app.utils.importer import parse_csv_file
from app.utils.balances import calculate_group_balances, simplify_debts

group_bp = Blueprint('group', __name__, url_prefix='/groups')

@group_bp.route('/')
@login_required
def index():
    active_memberships = GroupMember.query.filter_by(user_id=current_user.id, left_at=None).all()
    groups = [m.group for m in active_memberships]
    return render_template('group/index.html', groups=groups)

@group_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = GroupForm()
    if form.validate_on_submit():
        group = Group(name=form.name.data, description=form.description.data)
        db.session.add(group)
        db.session.flush() # flush to get group.id before commit
        
        member = GroupMember(user_id=current_user.id, group_id=group.id)
        db.session.add(member)
        db.session.commit()
        
        flash('Group created successfully!', 'success')
        return redirect(url_for('group.view', group_id=group.id))
    return render_template('group/create.html', form=form)

@group_bp.route('/<int:group_id>', methods=['GET', 'POST'])
@login_required
def view(group_id):
    group = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group.id, left_at=None).first()
    
    if not membership:
        flash('You are not an active member of this group.', 'danger')
        return redirect(url_for('group.index'))
    
    form = AddMemberForm()
    if form.validate_on_submit():
        user_to_add = User.query.filter_by(email=form.email.data).first()
        if not user_to_add:
            flash('User not found with that email.', 'danger')
        else:
            existing = GroupMember.query.filter_by(user_id=user_to_add.id, group_id=group.id).first()
            if existing and existing.left_at is None:
                flash('User is already an active member of the group.', 'info')
            else:
                if existing and existing.left_at is not None:
                    # User is rejoining
                    existing.left_at = None
                    existing.joined_at = datetime.now(timezone.utc)
                else:
                    new_member = GroupMember(user_id=user_to_add.id, group_id=group.id)
                    db.session.add(new_member)
                db.session.commit()
                flash('User added to the group successfully.', 'success')
        return redirect(url_for('group.view', group_id=group.id))
    
    # Calculate balances and simplified debts
    member_balances = calculate_group_balances(group.id)
    simplified_debts_list = simplify_debts(member_balances)
    
    from app.models.expense import Expense, Settlement
    expenses = Expense.query.filter_by(group_id=group.id).order_by(Expense.date.desc()).all()
    settlements = Settlement.query.filter_by(group_id=group.id).order_by(Settlement.date.desc()).all()
    
    active_memberships = GroupMember.query.filter_by(group_id=group.id, left_at=None).all()
    return render_template('group/view.html', group=group, memberships=active_memberships, form=form,
                           member_balances=member_balances, simplified_debts=simplified_debts_list,
                           expenses=expenses, settlements=settlements)

@group_bp.route('/<int:group_id>/leave', methods=['POST'])
@login_required
def leave(group_id):
    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group_id, left_at=None).first_or_404()
    membership.left_at = datetime.now(timezone.utc)
    db.session.commit()
    flash('You have left the group.', 'success')
    return redirect(url_for('group.index'))

@group_bp.route('/<int:group_id>/import', methods=['GET', 'POST'])
@login_required
def import_csv(group_id):
    group = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group.id, left_at=None).first()
    if not membership:
        flash('You are not an active member of this group.', 'danger')
        return redirect(url_for('group.index'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        exchange_rate_str = request.form.get('exchange_rate', '83.00')
        try:
            exchange_rate = Decimal(exchange_rate_str)
        except Exception:
            exchange_rate = Decimal('83.00')
            
        if file and file.filename.endswith('.csv'):
            file_content = file.read().decode('utf-8', errors='ignore')
            records, anomalies = parse_csv_file(file_content, exchange_rate)
            
            session['import_data'] = {
                'records': records,
                'anomalies': anomalies,
                'exchange_rate': float(exchange_rate),
                'group_id': group_id
            }
            session.modified = True
            
            return render_template('group/import_preview.html', group=group, records=records, anomalies=anomalies)
        else:
            flash('Please upload a valid CSV file.', 'danger')
            
    return render_template('group/import.html', group=group)

@group_bp.route('/<int:group_id>/import/confirm', methods=['POST'])
@login_required
def import_confirm(group_id):
    group = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group.id, left_at=None).first()
    if not membership:
        flash('You are not an active member of this group.', 'danger')
        return redirect(url_for('group.index'))
    
    import_data = session.get('import_data')
    if not import_data or import_data.get('group_id') != group_id:
        flash('No import session found or expired. Please upload again.', 'danger')
        return redirect(url_for('group.import_csv', group_id=group_id))
    
    records = import_data['records']
    anomalies = import_data['anomalies']
    exchange_rate = Decimal(str(import_data['exchange_rate']))
    
    unique_users = set()
    for rec in records:
        unique_users.add(rec['paid_by'])
        if rec['is_settlement']:
            unique_users.add(rec['payee'])
        else:
            for s in rec['splits']:
                unique_users.add(s['user'])
                
    user_mapping = {}
    from app.models.user import User
    from app.models.expense import Expense, ExpenseSplit, Settlement
    
    for username in unique_users:
        user = User.query.filter_by(username=username).first()
        if not user:
            hashed_pw = bcrypt.generate_password_hash('flatmates123').decode('utf-8')
            email = f"{username.lower()}@flatmates.local"
            if username == 'Priya':
                email = 'priya@flatmates.local'
            user = User(username=username, email=email, password=hashed_pw)
            db.session.add(user)
            db.session.flush()
        user_mapping[username] = user
        
        gm = GroupMember.query.filter_by(user_id=user.id, group_id=group.id).first()
        if not gm:
            joined_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
            left_at = None
            if username == 'Meera':
                left_at = datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
            elif username == 'Sam':
                joined_at = datetime(2026, 4, 8, tzinfo=timezone.utc)
                
            gm = GroupMember(user_id=user.id, group_id=group.id, joined_at=joined_at, left_at=left_at)
            db.session.add(gm)
        else:
            if username == 'Meera':
                gm.left_at = datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
            elif username == 'Sam':
                gm.joined_at = datetime(2026, 4, 8, tzinfo=timezone.utc)
    
    db.session.flush()
    
    import_report_lines = [
        "Expense Import Report",
        "=====================",
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Group: {group.name}",
        f"Exchange Rate: {exchange_rate} per USD\n",
        "Row Actions:"
    ]
    
    imported_count = 0
    skipped_count = 0
    
    for rec in records:
        row_idx = rec['row_index']
        is_checked = request.form.get(f'import_row_{row_idx}') == 'yes'
        
        row_anom = [a for a in anomalies if a['row'] == row_idx]
        issues_str = ""
        if row_anom:
            issues_str = "; ".join([issue['message'] for issue in row_anom[0]['issues']])
            
        if not is_checked:
            skipped_count += 1
            action_taken = "SKIPPED"
            import_report_lines.append(f"Row {row_idx}: {rec['description']} - {action_taken}")
            if issues_str:
                import_report_lines.append(f"  Anomalies Resolved: {issues_str}")
            continue
            
        rec_date = datetime.strptime(rec['date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
        
        if rec['is_settlement']:
            payer_user = user_mapping[rec['paid_by']]
            payee_user = user_mapping[rec['payee']]
            
            settlement = Settlement(
                group_id=group.id,
                payer_id=payer_user.id,
                payee_id=payee_user.id,
                amount=Decimal(str(rec['amount_inr'])),
                date=rec_date
            )
            db.session.add(settlement)
            action_taken = f"IMPORTED AS SETTLEMENT ({rec['paid_by']} paid {rec['payee']} ₹{rec['amount_inr']})"
        else:
            payer_user = user_mapping[rec['paid_by']]
            
            desc = rec['description']
            if rec['currency_original'] == 'USD':
                desc = f"{desc} (USD {rec['amount_original']} @ {exchange_rate})"
                
            expense = Expense(
                group_id=group.id,
                paid_by_id=payer_user.id,
                description=desc,
                amount=Decimal(str(rec['amount_inr'])),
                currency='INR',
                date=rec_date,
                split_type=rec['split_type'].upper()
            )
            db.session.add(expense)
            db.session.flush()
            
            for s in rec['splits']:
                split_user = user_mapping[s['user']]
                split_amt = Decimal(str(s['amount']))
                
                exp_split = ExpenseSplit(
                    expense_id=expense.id,
                    user_id=split_user.id,
                    amount=split_amt
                )
                db.session.add(exp_split)
                
            action_taken = f"IMPORTED AS EXPENSE (₹{rec['amount_inr']} split among: {', '.join([s['user'] for s in rec['splits']])})"
            
        import_report_lines.append(f"Row {row_idx}: {rec['description']} - {action_taken}")
        if issues_str:
            import_report_lines.append(f"  Anomalies Resolved: {issues_str}")
        imported_count += 1
        
    db.session.commit()
    
    import_report_content = "\n".join(import_report_lines)
    report_path = os.path.join(os.getcwd(), 'import_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(import_report_content)
        
    session.pop('import_data', None)
    
    flash(f"CSV import complete. {imported_count} rows imported, {skipped_count} rows skipped. See import_report.txt for details.", "success")
    return redirect(url_for('group.view', group_id=group.id))

@group_bp.route('/<int:group_id>/expenses/new', methods=['GET', 'POST'])
@login_required
def add_expense(group_id):
    group = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group.id, left_at=None).first()
    if not membership:
        flash('You are not an active member of this group.', 'danger')
        return redirect(url_for('group.index'))
    
    active_memberships = GroupMember.query.filter_by(group_id=group.id, left_at=None).all()
    members = [m.user for m in active_memberships]
    
    if request.method == 'POST':
        description = request.form.get('description')
        amount_str = request.form.get('amount')
        currency = request.form.get('currency', 'INR')
        paid_by_id = request.form.get('paid_by_id')
        date_str = request.form.get('date')
        split_type = request.form.get('split_type', 'EQUAL').upper()
        
        try:
            amount = Decimal(amount_str)
        except Exception:
            flash('Invalid amount entered.', 'danger')
            return render_template('group/expense_create.html', group=group, members=members)
            
        date = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc) if date_str else datetime.now(timezone.utc)
        
        from decimal import ROUND_HALF_UP
        if currency == 'USD':
            rate = Decimal('83.00')
            amount_inr = (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            description = f"{description} (USD {amount} @ {rate})"
            amount = amount_inr
            currency = 'INR'
        
        split_member_ids = []
        split_details = {}
        for m in members:
            if request.form.get(f'split_member_{m.id}') == 'yes':
                split_member_ids.append(m.id)
                val = request.form.get(f'split_val_{m.id}', '0')
                try:
                    split_details[m.id] = Decimal(val) if val else Decimal('0')
                except Exception:
                    split_details[m.id] = Decimal('0')
                    
        if not split_member_ids:
            flash('You must select at least one member to split with.', 'danger')
            return render_template('group/expense_create.html', group=group, members=members)
        
        # Create expense
        expense = Expense(
            group_id=group.id,
            paid_by_id=int(paid_by_id),
            description=description,
            amount=amount,
            currency='INR',
            date=date,
            split_type=split_type
        )
        db.session.add(expense)
        db.session.flush()
        
        # Calculate splits
        splits = []
        from app.models.expense import ExpenseSplit
        
        if split_type == 'EQUAL':
            share = (amount / len(split_member_ids)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            allocated = Decimal('0.00')
            for mid in split_member_ids[:-1]:
                splits.append((mid, share))
                allocated += share
            splits.append((split_member_ids[-1], amount - allocated))
            
        elif split_type == 'PERCENTAGE':
            total_pct = sum(split_details[mid] for mid in split_member_ids)
            allocated = Decimal('0.00')
            for i, mid in enumerate(split_member_ids):
                pct = split_details[mid]
                if total_pct > 0:
                    share = (amount * (pct / total_pct)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                else:
                    share = Decimal('0.00')
                if i < len(split_member_ids) - 1:
                    splits.append((mid, share))
                    allocated += share
                else:
                    splits.append((mid, amount - allocated))
                    
        elif split_type == 'UNEQUAL':
            total_amt = sum(split_details[mid] for mid in split_member_ids)
            allocated = Decimal('0.00')
            for i, mid in enumerate(split_member_ids):
                amt_val = split_details[mid]
                if total_amt > 0:
                    share = (amount * (amt_val / total_amt)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                else:
                    share = Decimal('0.00')
                if i < len(split_member_ids) - 1:
                    splits.append((mid, share))
                    allocated += share
                else:
                    splits.append((mid, amount - allocated))
                    
        elif split_type == 'SHARE':
            total_shares = sum(split_details[mid] for mid in split_member_ids)
            allocated = Decimal('0.00')
            for i, mid in enumerate(split_member_ids):
                sh = split_details[mid]
                if total_shares > 0:
                    share = (amount * (sh / total_shares)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                else:
                    share = Decimal('0.00')
                if i < len(split_member_ids) - 1:
                    splits.append((mid, share))
                    allocated += share
                else:
                    splits.append((mid, amount - allocated))
        
        # Save splits
        for mid, amt in splits:
            exp_split = ExpenseSplit(
                expense_id=expense.id,
                user_id=mid,
                amount=amt
            )
            db.session.add(exp_split)
            
        db.session.commit()
        flash('Expense created successfully!', 'success')
        return redirect(url_for('group.view', group_id=group.id))
        
    return render_template('group/expense_create.html', group=group, members=members)

@group_bp.route('/<int:group_id>/settlements/new', methods=['GET', 'POST'])
@login_required
def record_settlement(group_id):
    group = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group.id, left_at=None).first()
    if not membership:
        flash('You are not an active member of this group.', 'danger')
        return redirect(url_for('group.index'))
    
    active_memberships = GroupMember.query.filter_by(group_id=group.id, left_at=None).all()
    members = [m.user for m in active_memberships]
    
    if request.method == 'POST':
        payer_id = request.form.get('payer_id')
        payee_id = request.form.get('payee_id')
        amount_str = request.form.get('amount')
        date_str = request.form.get('date')
        
        if payer_id == payee_id:
            flash('Payer and Payee cannot be the same user.', 'danger')
            return render_template('group/settlement_create.html', group=group, members=members)
            
        try:
            amount = Decimal(amount_str)
        except Exception:
            flash('Invalid amount entered.', 'danger')
            return render_template('group/settlement_create.html', group=group, members=members)
            
        date = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc) if date_str else datetime.now(timezone.utc)
        
        from app.models.expense import Settlement
        settlement = Settlement(
            group_id=group.id,
            payer_id=int(payer_id),
            payee_id=int(payee_id),
            amount=amount,
            date=date
        )
        db.session.add(settlement)
        db.session.commit()
        
        flash('Settlement payment recorded successfully!', 'success')
        return redirect(url_for('group.view', group_id=group.id))
        
    return render_template('group/settlement_create.html', group=group, members=members)

@group_bp.route('/<int:group_id>/members/<int:user_id>/ledger', methods=['GET'])
@login_required
def member_ledger(group_id, user_id):
    group = Group.query.get_or_404(group_id)
    membership = GroupMember.query.filter_by(user_id=current_user.id, group_id=group.id, left_at=None).first()
    if not membership:
        flash('You are not an active member of this group.', 'danger')
        return redirect(url_for('group.index'))
        
    user = User.query.get_or_404(user_id)
    
    from app.models.expense import Expense, ExpenseSplit, Settlement
    
    expenses_paid = Expense.query.filter_by(group_id=group_id, paid_by_id=user_id).order_by(Expense.date.desc()).all()
    splits_owed = ExpenseSplit.query.join(Expense).filter(Expense.group_id == group_id, ExpenseSplit.user_id == user_id).order_by(Expense.date.desc()).all()
    
    settlements_paid = Settlement.query.filter_by(group_id=group_id, payer_id=user_id).order_by(Settlement.date.desc()).all()
    settlements_recv = Settlement.query.filter_by(group_id=group_id, payee_id=user_id).order_by(Settlement.date.desc()).all()
    
    total_paid = sum(e.amount for e in expenses_paid) or Decimal('0.00')
    total_splits = sum(s.amount for s in splits_owed) or Decimal('0.00')
    total_settlements_sent = sum(s.amount for s in settlements_paid) or Decimal('0.00')
    total_settlements_recv = sum(s.amount for s in settlements_recv) or Decimal('0.00')
    
    net_balance = total_paid - total_splits + total_settlements_sent - total_settlements_recv
    
    return render_template('group/ledger.html', group=group, user=user,
                           expenses_paid=expenses_paid, splits_owed=splits_owed,
                           settlements_paid=settlements_paid, settlements_received=settlements_recv,
                           total_paid=total_paid, total_splits=total_splits,
                           total_settlements_sent=total_settlements_sent,
                           total_settlements_recv=total_settlements_recv,
                           net_balance=net_balance)