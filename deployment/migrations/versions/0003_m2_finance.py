"""M2 Markdown conversions and extracted finance data."""
from alembic import op
import sqlalchemy as sa

revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('document_conversions',
        sa.Column('id',sa.String(32),primary_key=True),
        sa.Column('project_id',sa.String(32),sa.ForeignKey('projects.id'),nullable=False),
        sa.Column('document_id',sa.String(32),sa.ForeignKey('documents.id'),nullable=False),
        sa.Column('original_sha256',sa.String(64),nullable=False),
        sa.Column('tool',sa.String(30),nullable=False),
        sa.Column('tool_version',sa.String(100),nullable=False),
        sa.Column('state',sa.String(30),nullable=False),
        sa.Column('markdown_path',sa.Text(),nullable=True),
        sa.Column('markdown_sha256',sa.String(64),nullable=True),
        sa.Column('error',sa.String(100),nullable=True),
        sa.Column('created_at',sa.Float(),nullable=False),
        sa.Column('completed_at',sa.Float(),nullable=True))
    op.create_table('financial_statements',
        sa.Column('id',sa.String(32),primary_key=True),
        sa.Column('project_id',sa.String(32),sa.ForeignKey('projects.id'),nullable=False),
        sa.Column('document_id',sa.String(32),sa.ForeignKey('documents.id'),nullable=False),
        sa.Column('conversion_id',sa.String(32),sa.ForeignKey('document_conversions.id'),nullable=False),
        sa.Column('statement_type',sa.String(30),nullable=False),
        sa.Column('entity',sa.String(200),nullable=False),
        sa.Column('scope',sa.String(20),nullable=False),
        sa.Column('period',sa.String(50),nullable=False),
        sa.Column('period_normalized',sa.String(50),nullable=True),
        sa.Column('period_kind',sa.String(20),nullable=True),
        sa.Column('currency',sa.String(10),nullable=False),
        sa.Column('raw_unit',sa.String(20),nullable=False),
        sa.Column('unit_scale',sa.String(20),nullable=True),
        sa.Column('source_start_line',sa.Integer(),nullable=False),
        sa.Column('source_end_line',sa.Integer(),nullable=False),
        sa.Column('state',sa.String(30),nullable=False),
        sa.Column('issues',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False))
    op.create_table('financial_items',
        sa.Column('id',sa.String(32),primary_key=True),
        sa.Column('statement_id',sa.String(32),sa.ForeignKey('financial_statements.id'),nullable=False),
        sa.Column('concept',sa.String(80),nullable=False),
        sa.Column('source_name',sa.String(200),nullable=False),
        sa.Column('raw_value',sa.String(100),nullable=False),
        sa.Column('raw_unit',sa.String(20),nullable=False),
        sa.Column('normalized_value',sa.String(100),nullable=True),
        sa.Column('source_text',sa.Text(),nullable=False),
        sa.Column('source_start_line',sa.Integer(),nullable=False),
        sa.Column('source_end_line',sa.Integer(),nullable=False),
        sa.Column('status',sa.String(40),nullable=False),
        sa.Column('confirmed_by',sa.String(32),sa.ForeignKey('users.id'),nullable=True),
        sa.Column('confirmed_at',sa.Float(),nullable=True),
        sa.Column('confirmation_reason',sa.Text(),nullable=True))

def downgrade():
    op.drop_table('financial_items')
    op.drop_table('financial_statements')
    op.drop_table('document_conversions')
