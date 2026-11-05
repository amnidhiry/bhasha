"""language-neutral core: active language, per-language frequencies and sentences, dictionary

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-05 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def _lang() -> sa.Column:
    return sa.Column('language', sa.String(length=16), nullable=False, server_default='zh')


def _rebuild_frequency(pk: list[str], cols: str, select: str) -> None:
    """SQLite can't change a primary key in place: copy into a new table."""
    extra = [_lang()] if 'language' in pk else []
    op.create_table(
        '_word_frequency_new', *extra,
        sa.Column('word', sa.String(length=64), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('per_million', sa.Float(), nullable=False),
        sa.Column('cd_percent', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint(*pk),
    )
    op.execute(f"INSERT INTO _word_frequency_new ({cols}) SELECT {select} FROM word_frequency")
    op.drop_index('ix_word_frequency_rank', table_name='word_frequency')
    op.drop_table('word_frequency')
    op.rename_table('_word_frequency_new', 'word_frequency')
    op.create_index('ix_word_frequency_rank', 'word_frequency', ['rank'])


def upgrade() -> None:
    pg = op.get_bind().dialect.name == 'postgresql'
    with op.batch_alter_table('app_user') as b:
        b.add_column(sa.Column('active_language', sa.String(length=16), nullable=False, server_default='zh'))
    for table in ('journal_entry', 'tutor_session'):
        with op.batch_alter_table(table) as b:
            b.add_column(_lang())
    with op.batch_alter_table('example_sentence') as b:
        b.add_column(_lang())
        b.create_index('ix_example_sentence_language', ['language'])

    # word_frequency: primary key (word) -> (language, word)
    if pg:
        op.drop_constraint('word_frequency_pkey', 'word_frequency', type_='primary')
        op.add_column('word_frequency', _lang())
        op.create_primary_key('word_frequency_pkey', 'word_frequency', ['language', 'word'])
    else:
        _rebuild_frequency(['language', 'word'], "language, word, rank, per_million, cd_percent",
                           "'zh', word, rank, per_million, cd_percent")

    op.create_table(
        'dictionary_entry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('language', sa.String(length=16), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('headword', sa.String(length=128), nullable=False),
        sa.Column('reading', sa.String(length=256), nullable=False, server_default=''),
        sa.Column('pos', sa.String(length=32), nullable=True),
        sa.Column('glosses', JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column('tags', JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column('license', sa.String(length=32), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dictionary_lang_head', 'dictionary_entry', ['language', 'headword'])


def downgrade() -> None:
    pg = op.get_bind().dialect.name == 'postgresql'
    op.drop_index('ix_dictionary_lang_head', table_name='dictionary_entry')
    op.drop_table('dictionary_entry')
    op.execute("DELETE FROM word_frequency WHERE language <> 'zh'")
    if pg:
        op.drop_constraint('word_frequency_pkey', 'word_frequency', type_='primary')
        op.drop_column('word_frequency', 'language')
        op.create_primary_key('word_frequency_pkey', 'word_frequency', ['word'])
    else:
        _rebuild_frequency(['word'], "word, rank, per_million, cd_percent", "word, rank, per_million, cd_percent")
    with op.batch_alter_table('example_sentence') as b:
        b.drop_index('ix_example_sentence_language')
        b.drop_column('language')
    for table in ('tutor_session', 'journal_entry'):
        with op.batch_alter_table(table) as b:
            b.drop_column('language')
    with op.batch_alter_table('app_user') as b:
        b.drop_column('active_language')
