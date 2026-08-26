"""fix_is_active_default_and_not_null

Revision ID: 8676506d8095
Revises: 2527093a50e6
Create Date: 2026-08-26 17:30:00.000000

`is_active` sütunu 2527093a50e6 ile server_default olmadan eklenmişti. Sonuç:
ORM dışında (düz SQL, veri aktarımı, seed script'i) eklenen her kullanıcı satırında
değer NULL kalıyor ve `get_current_user` bu kullanıcıya 403 verip kalıcı olarak
kilitliyordu. Bu migration mevcut NULL'ları doldurur, varsayılanı veritabanı
seviyesine taşır ve sütunu NOT NULL yapar.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8676506d8095'
down_revision: Union[str, Sequence[str], None] = '2527093a50e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1) Mevcut NULL satırları doldur (kilitlenmiş kullanıcıları geri aç)
    op.execute("UPDATE users SET is_active = true WHERE is_active IS NULL")
    # 2) Varsayılanı veritabanına taşı ve sütunu NOT NULL yap
    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=None,
        nullable=True,
    )
