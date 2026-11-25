from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.core.models import Base
from app.modules.accounts import models as account_models
from app.modules.audit import models as audit_models
from app.modules.facilities import models as facility_models
from app.modules.trips import models as trip_models
from app.modules.weighings import models as weighing_models
from app.modules.goods import models as goods_models
from app.modules.scale_ingestion import models as scale_ingestion_models
from app.modules.vehicle_pilot import models as vehicle_pilot_models
from app.modules.drum_processing import models as drum_models

target_metadata = Base.metadata
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
