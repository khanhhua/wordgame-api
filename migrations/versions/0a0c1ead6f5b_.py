"""empty message

Revision ID: 0a0c1ead6f5b
Revises: f2177fdb08cc
Create Date: 2020-03-03 22:05:41.849501

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0a0c1ead6f5b'
down_revision = 'f2177fdb08cc'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('session', sa.Column('status', sa.Integer(), nullable=False))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('session', 'status')
    # ### end Alembic commands ###
