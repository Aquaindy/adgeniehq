"""Help audio assets: cached ElevenLabs narration for Help articles

Generate-on-first-play narration for the built-in Help/Knowledge-Base is cached
globally (help content is platform-level) keyed by (topic_id, content_hash,
voice_id), so a given article+voice is synthesized once and served to everyone.

Revision ID: f8c3a1e7b9d2
Revises: e7b2c4d6f8a0
Create Date: 2026-07-17 02:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8c3a1e7b9d2'
down_revision: Union[str, None] = 'e7b2c4d6f8a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    help_audio_status = sa.Enum(
        'generating', 'ready', 'failed', name='help_audio_status'
    )
    op.create_table(
        'help_audio_assets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('topic_id', sa.String(length=64), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('voice_id', sa.String(length=64), nullable=False),
        sa.Column('url', sa.String(length=1024), nullable=True),
        sa.Column('status', help_audio_status, nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic_id', 'content_hash', 'voice_id', name='uq_help_audio_topic_hash_voice'),
    )
    op.create_index(
        op.f('ix_help_audio_assets_topic_id'),
        'help_audio_assets',
        ['topic_id'],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_help_audio_assets_topic_id'), table_name='help_audio_assets')
    op.drop_table('help_audio_assets')
    sa.Enum(name='help_audio_status').drop(op.get_bind(), checkfirst=True)
