from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, timezone
from app import db
from app.models.group import Group, GroupMember
from app.models.user import User
from app.forms import GroupForm, AddMemberForm

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