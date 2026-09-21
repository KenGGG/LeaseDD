"""Minimal enterprise-warning financial imports."""
from alembic import op
import sqlalchemy as sa

revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('enterprise_bindings',
        sa.Column('id',sa.String(32),primary_key=True),
        sa.Column('project_id',sa.String(32),sa.ForeignKey('projects.id'),nullable=False,unique=True),
        sa.Column('company_code',sa.String(100),nullable=False),
        sa.Column('company_name',sa.String(200),nullable=False),
        sa.Column('identity',sa.JSON(),nullable=False),
        sa.Column('created_by',sa.String(32),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False))
    op.create_table('enterprise_imports',
        sa.Column('id',sa.String(32),primary_key=True),
        sa.Column('project_id',sa.String(32),sa.ForeignKey('projects.id'),nullable=False),
        sa.Column('task_id',sa.String(32),sa.ForeignKey('tasks.id'),nullable=False,unique=True),
        sa.Column('state',sa.String(30),nullable=False),
        sa.Column('quality_state',sa.String(30),nullable=False),
        sa.Column('module_status',sa.JSON(),nullable=False),
        sa.Column('error',sa.String(100),nullable=True),
        sa.Column('content_sha256',sa.String(64),nullable=True),
        sa.Column('started_at',sa.Float(),nullable=True),
        sa.Column('completed_at',sa.Float(),nullable=True))
    op.create_table('enterprise_financial_data',
        sa.Column('id',sa.String(32),primary_key=True),
        sa.Column('import_id',sa.String(32),sa.ForeignKey('enterprise_imports.id'),nullable=False),
        sa.Column('category',sa.String(50),nullable=False),
        sa.Column('module_key',sa.String(100),nullable=False),
        sa.Column('module_name',sa.String(200),nullable=False),
        sa.Column('module_order',sa.Integer(),nullable=False),
        sa.Column('endpoint_path',sa.Text(),nullable=False),
        sa.Column('request_params',sa.JSON(),nullable=False),
        sa.Column('raw_payload',sa.JSON(),nullable=False),
        sa.Column('parsed_payload',sa.JSON(),nullable=False),
        sa.Column('response_sha256',sa.String(64),nullable=False),
        sa.Column('state',sa.String(30),nullable=False),
        sa.Column('error',sa.String(100),nullable=True),
        sa.Column('collected_at',sa.Float(),nullable=False),
        sa.UniqueConstraint('import_id','module_key'))

def downgrade():
    op.drop_table('enterprise_financial_data')
    op.drop_table('enterprise_imports')
    op.drop_table('enterprise_bindings')
