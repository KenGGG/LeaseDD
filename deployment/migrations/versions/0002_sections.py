"""Frozen LeaseDD database schema migration."""
from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('section_revisions',
        sa.Column('id', sa.String(length=32), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(length=32), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('input_revision', sa.Integer(), nullable=False),
        sa.Column('draft', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(length=32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.UniqueConstraint('project_id', 'version'),
    )

def downgrade():
    op.drop_table('section_revisions')
