"""initial schema

Portable column types only (no app imports): UTC timestamps are DateTime(timezone=True); lists/dicts are JSON.

Revision ID: 0001
Revises: 
Create Date: 2026-11-17 12:00:50.088893
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    
    op.create_table('teams',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('office', sa.String(length=200), nullable=True),
    sa.Column('open_time', sa.String(length=5), nullable=False),
    sa.Column('close_time', sa.String(length=5), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('invite_token', sa.String(length=128), nullable=True),
    sa.Column('invite_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_teams')),
    sa.UniqueConstraint('invite_token', name=op.f('uq_teams_invite_token'))
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('display_name', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('api_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('scopes', sa.JSON(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('prefix', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_api_tokens_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_api_tokens_token_hash'))
    )
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('idempotency_keys',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('fingerprint', sa.Text(), nullable=False),
    sa.Column('status', sa.Integer(), nullable=False),
    sa.Column('body', sa.JSON(), nullable=False),
    sa.Column('headers', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_idempotency_keys_user_id_users')),
    sa.PrimaryKeyConstraint('user_id', 'key', name=op.f('pk_idempotency_keys'))
    )
    with op.batch_alter_table('idempotency_keys', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_idempotency_keys_created_at'), ['created_at'], unique=False)

    op.create_table('memberships',
    sa.Column('team_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_memberships_team_id_teams'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_memberships_user_id_users')),
    sa.PrimaryKeyConstraint('team_id', 'user_id', name=op.f('pk_memberships'))
    )
    with op.batch_alter_table('memberships', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_memberships_user_id'), ['user_id'], unique=False)

    op.create_table('restaurants',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('team_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('cuisine', sa.String(length=200), nullable=True),
    sa.Column('address', sa.String(length=500), nullable=True),
    sa.Column('website_url', sa.String(length=2000), nullable=True),
    sa.Column('map_url', sa.String(length=2000), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_restaurants_created_by_users')),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_restaurants_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_restaurants'))
    )
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_restaurants_team_id'), ['team_id'], unique=False)

    op.create_table('sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_sessions_token_hash'))
    )
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('polls',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('team_id', sa.Uuid(), nullable=False),
    sa.Column('poll_date', sa.Date(), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('opens_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closes_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('candidate_ids', sa.JSON(), nullable=False),
    sa.Column('seed', sa.String(length=64), nullable=False),
    sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('winner_id', sa.Uuid(), nullable=True),
    sa.Column('no_winner', sa.Boolean(), nullable=False),
    sa.Column('tie_break', sa.String(length=32), nullable=True),
    sa.Column('final_scores', sa.JSON(), nullable=True),
    sa.Column('frozen_names', sa.JSON(), nullable=False),
    sa.Column('opened_emitted', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_polls_team_id_teams'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['winner_id'], ['restaurants.id'], name=op.f('fk_polls_winner_id_restaurants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_polls')),
    sa.UniqueConstraint('team_id', 'poll_date', name=op.f('uq_polls_team_id_poll_date'))
    )
    op.create_table('ballots',
    sa.Column('poll_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('choices', sa.JSON(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('display_name', sa.String(length=254), nullable=True),
    sa.ForeignKeyConstraint(['poll_id'], ['polls.id'], name=op.f('fk_ballots_poll_id_polls'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_ballots_user_id_users')),
    sa.PrimaryKeyConstraint('poll_id', 'user_id', name=op.f('pk_ballots'))
    )
    with op.batch_alter_table('ballots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ballots_user_id'), ['user_id'], unique=False)

    


def downgrade() -> None:
    
    with op.batch_alter_table('ballots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ballots_user_id'))

    op.drop_table('ballots')
    op.drop_table('polls')
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sessions_user_id'))

    op.drop_table('sessions')
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_restaurants_team_id'))

    op.drop_table('restaurants')
    with op.batch_alter_table('memberships', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_memberships_user_id'))

    op.drop_table('memberships')
    with op.batch_alter_table('idempotency_keys', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_idempotency_keys_created_at'))

    op.drop_table('idempotency_keys')
    with op.batch_alter_table('api_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_tokens_user_id'))

    op.drop_table('api_tokens')
    op.drop_table('users')
    op.drop_table('teams')
    
