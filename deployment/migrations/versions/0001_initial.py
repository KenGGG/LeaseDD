"""Frozen LeaseDD database schema migration."""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('audit',
        sa.Column('id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(length=32), nullable=True),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('action', sa.String(length=80), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
    )
    op.create_table('projects',
        sa.Column('id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('metrics_revision', sa.Integer(), nullable=False),
        sa.Column('section', sa.JSON(), nullable=False),
        sa.Column('section_version', sa.Integer(), nullable=False),
        sa.Column('section_revision', sa.Integer(), nullable=False),
        sa.Column('production_template_status', sa.String(length=30), nullable=False),
    )
    op.create_table('settings',
        sa.Column('key', sa.String(length=40), nullable=False, primary_key=True),
        sa.Column('value', sa.JSON(), nullable=False),
    )
    op.create_table('users',
        sa.Column('id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('admin', sa.Boolean(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('username'),
    )
    op.create_table('documents',
        sa.Column('id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(length=32), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('model_allowed', sa.Boolean(), nullable=False),
        sa.Column('parse_state', sa.String(length=50), nullable=False),
        sa.Column('created_by', sa.String(length=32), sa.ForeignKey('users.id'), nullable=False),
    )
    op.create_table('login_sessions',
        sa.Column('token_hash', sa.String(length=64), nullable=False, primary_key=True),
        sa.Column('user_id', sa.String(length=32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('csrf', sa.String(length=64), nullable=False),
        sa.Column('expires', sa.Float(), nullable=False),
    )
    op.create_table('members',
        sa.Column('id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(length=32), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('user_id', sa.String(length=32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.UniqueConstraint('project_id', 'user_id'),
    )
    op.create_table('tasks',
        sa.Column('id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(length=32), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('mode', sa.String(length=30), nullable=False),
        sa.Column('state', sa.String(length=30), nullable=False),
        sa.Column('input_revision', sa.Integer(), nullable=False),
        sa.Column('input_hash', sa.String(length=64), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('lease_until', sa.Float(), nullable=False),
        sa.Column('lease_token', sa.String(length=32), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('reason', sa.String(length=100), nullable=True),
        sa.Column('created_by', sa.String(length=32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
    )
    op.create_table('exports',
        sa.Column('id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(length=32), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('task_id', sa.String(length=32), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.UniqueConstraint('task_id'),
    )
    op.create_table('fact_batches',
        sa.Column('id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(length=32), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('document_id', sa.String(length=32), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.String(length=32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
    )

def downgrade():
    op.drop_table('fact_batches')
    op.drop_table('exports')
    op.drop_table('tasks')
    op.drop_table('members')
    op.drop_table('login_sessions')
    op.drop_table('documents')
    op.drop_table('users')
    op.drop_table('settings')
    op.drop_table('projects')
    op.drop_table('audit')
