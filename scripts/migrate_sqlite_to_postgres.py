from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import MetaData, create_engine, select


TABLE_ORDER = [
    "users",
    "accounts",
    "categories",
    "mapping_rules",
    "budget_settings",
    "import_batches",
    "import_previews",
    "transactions",
    "year_closes",
    "year_category_aggregates",
    "historical_reports",
]


def main() -> None:
    source_path = Path(os.environ.get("SRC_SQLITE_PATH", ".data/personal_finance.db")).resolve()
    target_url = os.environ["DST_DATABASE_URL"]

    source_engine = create_engine(f"sqlite:///{source_path}", future=True)
    target_engine = create_engine(target_url, future=True)

    source_meta = MetaData()
    source_meta.reflect(bind=source_engine)
    target_meta = MetaData()
    target_meta.reflect(bind=target_engine)

    with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
        for table_name in reversed(TABLE_ORDER):
            if table_name in target_meta.tables:
                target_conn.execute(target_meta.tables[table_name].delete())

        for table_name in TABLE_ORDER:
            source_table = source_meta.tables.get(table_name)
            target_table = target_meta.tables.get(table_name)
            if source_table is None or target_table is None:
                continue
            rows = [dict(row._mapping) for row in source_conn.execute(select(source_table))]
            if rows:
                target_conn.execute(target_table.insert(), rows)
            print(f"{table_name}: {len(rows)}")


if __name__ == "__main__":
    main()
