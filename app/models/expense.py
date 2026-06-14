from datetime import datetime, timezone
from app import db

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    paid_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='INR')
    date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    split_type = db.Column(db.String(20), nullable=False, default='EQUAL')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    group = db.relationship('Group', backref=db.backref('expenses', lazy='dynamic'))
    paid_by = db.relationship('User', backref=db.backref('expenses_paid', lazy='dynamic'))
    splits = db.relationship('ExpenseSplit', back_populates='expense', cascade='all, delete-orphan')

class ExpenseSplit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expense.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    expense = db.relationship('Expense', back_populates='splits')
    user = db.relationship('User', backref=db.backref('expense_splits', lazy='dynamic'))

class Settlement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    payer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    payee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    group = db.relationship('Group', backref=db.backref('settlements', lazy='dynamic'))
    payer = db.relationship('User', foreign_keys=[payer_id], backref=db.backref('settlements_paid', lazy='dynamic'))
    payee = db.relationship('User', foreign_keys=[payee_id], backref=db.backref('settlements_received', lazy='dynamic'))