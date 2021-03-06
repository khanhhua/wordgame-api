"""empty message

Revision ID: ab33d8711d64
Revises: 0a0c1ead6f5b
Create Date: 2020-03-03 23:48:07.415642

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab33d8711d64'
down_revision = '0a0c1ead6f5b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('term_stat', sa.Column('seconds', sa.Integer(), nullable=False, comment='Seconds taken to respond to this term'))
    op.add_column('term_stat', sa.Column('seconds_correct', sa.Integer(), nullable=True, comment='Seconds taken to correctly answer this term'))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('term_stat', 'seconds_correct')
    op.drop_column('term_stat', 'seconds')
    # ### end Alembic commands ###
