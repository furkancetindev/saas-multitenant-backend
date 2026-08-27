import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# 1) Proje ana dizinini sisteme tanıtıyoruz ki import hatası almayalım
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 2) Veritabanı URL'mizi ve Base objemizi çekiyoruz
from core.config import settings
from database import Base

# 3) Alembic'in tabloları algılaması için modelleri buraya import ETMELİYİZ!
from models.domain import Tenant, User, Task

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 4) alembic.ini içindeki sqlalchemy.url ayarını ezerek .env'deki URL'i kullanıyoruz.
#
#    Migration'lar DDL çalıştırır (CREATE TABLE, ALTER TABLE, CREATE POLICY),
#    uygulamanın bağlandığı kısıtlı rol ise bunu yapamaz — bilerek yapamaz.
#    Bu yüzden burada migration_database_url tercih edilir; verilmemişse
#    database_url'e düşülür.
#
#    .replace("%", "%%") gerekli: set_main_option değeri ConfigParser'a verir ve
#    orada "%" biçim karakteridir. Parolasında "%" geçen biri aksi hâlde
#    anlaşılmaz bir InterpolationSyntaxError alır.
db_url = settings.migration_database_url or settings.database_url
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 5) Alembic'e target_metadata'yı gösteriyoruz (autogenerate desteği için)
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()