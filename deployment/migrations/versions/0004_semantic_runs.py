"""Immutable Agnes semantic extraction runs."""
from alembic import op
import sqlalchemy as sa

revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('extraction_runs',
        sa.Column('id',sa.String(32),primary_key=True),
        sa.Column('task_id',sa.String(32),sa.ForeignKey('tasks.id'),nullable=False,unique=True),
        sa.Column('conversion_id',sa.String(32),sa.ForeignKey('document_conversions.id'),nullable=False),
        sa.Column('project_id',sa.String(32),sa.ForeignKey('projects.id'),nullable=False),
        sa.Column('document_id',sa.String(32),sa.ForeignKey('documents.id'),nullable=False),
        sa.Column('pipeline_version',sa.String(50),nullable=False),
        sa.Column('state',sa.String(30),nullable=False),
        sa.Column('manifest',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False))
    with op.batch_alter_table('financial_statements') as batch:
        batch.add_column(sa.Column('run_id',sa.String(32),nullable=True))
        batch.create_foreign_key('fk_financial_statements_run','extraction_runs',['run_id'],['id'])
    with op.batch_alter_table('financial_items') as batch:
        batch.add_column(sa.Column('evidence',sa.JSON(),nullable=False,server_default=sa.text("'{}'")))

def downgrade():
    with op.batch_alter_table('financial_items') as batch:batch.drop_column('evidence')
    with op.batch_alter_table('financial_statements') as batch:
        batch.drop_constraint('fk_financial_statements_run',type_='foreignkey')
        batch.drop_column('run_id')
    op.drop_table('extraction_runs')
