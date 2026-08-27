"""enable_rls_on_tasks

Revision ID: 3831f9c1e1fb
Revises: 8676506d8095
Create Date: 2026-08-26 20:15:00.000000

Kiracı izolasyonunun ikinci katmanı: PostgreSQL Row-Level Security.

Birinci katman, repository sorgularındaki elle `tenant_id` filtreleri. O katman
insan disiplinine dayanır — biri bir gün filtreyi yazmayı unutur. Bu migration
kuralı veritabanına taşır: kod filtreyi unutsa bile Postgres satırı vermez.

Üç detay, üçü de atlanırsa politika sessizce etkisiz kalır:

1. `FORCE` — RLS varsayılan olarak tablo SAHİBİNE uygulanmaz. Uygulama rolü
   tabloların sahibi değil (bkz. scripts/setup_db_role.py), yani teknik olarak
   şart değil; yine de savunma derinliği için açıyoruz.
   Not: superuser'ı ne `FORCE` ne başka bir şey durdurur — uygulamanın
   superuser ile bağlanmaması bu yüzden pazarlık konusu değil.

2. `NULLIF(current_setting('app.tenant_id', true), '')` — üç parçası da gerekli.

   `current_setting(..., true)`: ikinci argüman `true`, ayar hiç tanımlanmamışsa
   hata yerine NULL döndürür.

   `NULLIF(..., '')`: asıl tuzak burada. `set_config(..., true)` ile bir kez
   ayar yapılmış bir BAĞLANTIDA transaction bittiğinde değer NULL'a değil BOŞ
   DİZGEYE döner. Bağlantı havuzlu bir uygulamada bu, ikinci isteğinden sonra
   her bağlantının başına gelir. `''::uuid` ise hata fırlatır — yani NULLIF
   olmadan politika "0 satır" yerine "500 Internal Server Error" üretirdi.
   Fail-closed'in anlamı boş sonuçtur, patlamak değil.

   Sonuç: bağlam kurulmamışsa karşılaştırma NULL olur, hiçbir satır eşleşmez.
   Unutulan kiracı bağlamı veri sızdırmaz, isteği boş bırakır.

3. `WITH CHECK` — `USING` okumayı filtreler, `WITH CHECK` yazmayı doğrular.
   İkincisi olmasa bir kiracı, başka bir kiracının `tenant_id`'siyle satır
   ekleyebilirdi: kendi göremediği ama karşı tarafın gördüğü bir satır.

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '3831f9c1e1fb'
down_revision: Union[str, Sequence[str], None] = '8676506d8095'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE tasks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tasks FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON tasks
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tasks")
    op.execute("ALTER TABLE tasks NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tasks DISABLE ROW LEVEL SECURITY")
