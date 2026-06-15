from decimal import Decimal
from sqlalchemy.sql import func
from app.models.expense import Expense, ExpenseSplit, Settlement
from app.models.group import GroupMember
from app.models.user import User

def calculate_group_balances(group_id):
    """
    Computes the net balance for all members of a group.
    Returns:
        member_balances: dict mapping user_id -> dict with 'user', 'paid_expenses', 'split_expenses', 'settlements_paid', 'settlements_received', 'net_balance'
    """
    # Fetch all members (active and inactive)
    memberships = GroupMember.query.filter_by(group_id=group_id).all()
    member_balances = {}

    for m in memberships:
        user = m.user
        
        # 1. Total paid for expenses
        paid_sum = Expense.query.filter_by(group_id=group_id, paid_by_id=user.id).with_entities(func.sum(Expense.amount)).scalar() or Decimal('0.00')
        
        # 2. Total splits owed
        split_sum = ExpenseSplit.query.join(Expense).filter(Expense.group_id == group_id, ExpenseSplit.user_id == user.id).with_entities(func.sum(ExpenseSplit.amount)).scalar() or Decimal('0.00')
        
        # 3. Total settlements paid
        settlements_paid = Settlement.query.filter_by(group_id=group_id, payer_id=user.id).with_entities(func.sum(Settlement.amount)).scalar() or Decimal('0.00')
        
        # 4. Total settlements received
        settlements_rec = Settlement.query.filter_by(group_id=group_id, payee_id=user.id).with_entities(func.sum(Settlement.amount)).scalar() or Decimal('0.00')
        
        # Net balance formula
        net_balance = paid_sum - split_sum + settlements_paid - settlements_rec
        
        member_balances[user.id] = {
            'user': user,
            'paid_expenses': paid_sum,
            'split_expenses': split_sum,
            'settlements_paid': settlements_paid,
            'settlements_received': settlements_rec,
            'net_balance': net_balance
        }
        
    return member_balances

def simplify_debts(member_balances):
    """
    Greedy debt simplification algorithm.
    Takes the output of calculate_group_balances.
    Returns:
        simplified_settlements: list of dicts: {'payer': User, 'payee': User, 'amount': Decimal}
    """
    # Filter into debtors and creditors
    debtors = []
    creditors = []
    
    for user_id, info in member_balances.items():
        bal = info['net_balance']
        # Use a small threshold to avoid floating-point / rounding noise
        if bal < Decimal('-0.009'):
            debtors.append({'user': info['user'], 'balance': -bal}) # store as positive for convenience
        elif bal > Decimal('0.009'):
            creditors.append({'user': info['user'], 'balance': bal})
            
    # Sort so we always match the largest debtor and creditor
    debtors.sort(key=lambda x: x['balance'], reverse=True)
    creditors.sort(key=lambda x: x['balance'], reverse=True)
    
    simplified_settlements = []
    
    while debtors and creditors:
        debtor = debtors[0]
        creditor = creditors[0]
        
        # Settle the minimum of what debtor owes and what creditor is owed
        amount_to_settle = min(debtor['balance'], creditor['balance'])
        
        if amount_to_settle > Decimal('0.01'):
            simplified_settlements.append({
                'payer': debtor['user'],
                'payee': creditor['user'],
                'amount': amount_to_settle.quantize(Decimal('0.01'))
            })
            
        # Update their balances
        debtor['balance'] -= amount_to_settle
        creditor['balance'] -= amount_to_settle
        
        # Remove if settled
        if debtor['balance'] < Decimal('0.019'):
            debtors.pop(0)
        else:
            debtors.sort(key=lambda x: x['balance'], reverse=True)
            
        if creditor['balance'] < Decimal('0.019'):
            creditors.pop(0)
        else:
            creditors.sort(key=lambda x: x['balance'], reverse=True)
            
    return simplified_settlements
