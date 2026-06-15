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
    
    active_memberships = GroupMember.query.filter_by(group_id=group.id, left_at=None).all()
    return render_template('group/view.html', group=group, memberships=active_memberships, form=form)

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
            
            expense = Expense(
                group_id=group.id,
                paid_by_id=payer_user.id,
                description=rec['description'],
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