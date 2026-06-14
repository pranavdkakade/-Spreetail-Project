from datetime import datetime, timezone
from app import db

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    memberships = db.relationship('GroupMember', back_populates='group', lazy='dynamic')

class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    left_at = db.Column(db.DateTime, nullable=True) # None means active member

    user = db.relationship('User', backref=db.backref('memberships', lazy='dynamic'))
    group = db.relationship('Group', back_populates='memberships')
