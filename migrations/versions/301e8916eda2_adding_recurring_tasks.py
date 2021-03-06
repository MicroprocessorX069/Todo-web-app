"""Adding recurring tasks

Revision ID: 301e8916eda2
Revises: 40450c3e2368
Create Date: 2020-02-04 19:11:46.168999

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '301e8916eda2'
down_revision = '40450c3e2368'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('challengers', sa.Column('task_id', sa.Integer(), nullable=True))
    op.drop_constraint(None, 'challengers', type_='foreignkey')
    op.create_foreign_key(None, 'challengers', 'task', ['task_id'], ['id'])
    op.drop_column('challengers', 'challenge_id')
    op.drop_column('challengers', 'id')
    op.drop_constraint(None, 'task', type_='foreignkey')
    op.drop_column('task', 'challenger_id')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('task', sa.Column('challenger_id', sa.INTEGER(), nullable=True))
    op.create_foreign_key(None, 'task', 'challengers', ['challenger_id'], ['id'])
    op.add_column('challengers', sa.Column('id', sa.INTEGER(), nullable=False))
    op.add_column('challengers', sa.Column('challenge_id', sa.INTEGER(), nullable=True))
    op.drop_constraint(None, 'challengers', type_='foreignkey')
    op.create_foreign_key(None, 'challengers', 'challenge', ['challenge_id'], ['id'])
    op.drop_column('challengers', 'task_id')
    # ### end Alembic commands ###
