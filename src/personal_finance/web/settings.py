from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from personal_finance.config import PROJECT_ROOT


@dataclass(frozen=True)
class WebSettings:
    app_name: str
    secret_key: str
    database_url: str
    google_client_id: str
    google_client_secret: str
    openai_api_key: str
    openai_model: str
    finance_root: Path
    preview_root: Path
    upload_root: Path
    allow_dev_login: bool
    allowed_google_email: str
    public_base_url: str


def load_web_settings() -> WebSettings:
    data_root = PROJECT_ROOT / ".data"
    preview_root = data_root / "previews"
    upload_root = data_root / "uploads"
    data_root.mkdir(parents=True, exist_ok=True)
    preview_root.mkdir(parents=True, exist_ok=True)
    upload_root.mkdir(parents=True, exist_ok=True)

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        db_user = os.environ.get("DB_USER", "").strip()
        db_password = os.environ.get("DB_PASSWORD", "").strip()
        db_name = os.environ.get("DB_NAME", "").strip()
        db_host = os.environ.get("DB_HOST", "").strip()
        cloudsql_connection_name = os.environ.get("CLOUDSQL_CONNECTION_NAME", "").strip()
        if db_user and db_password and db_name and cloudsql_connection_name:
            database_url = (
                f"postgresql+psycopg://{db_user}:{db_password}@/{db_name}"
                f"?host=/cloudsql/{cloudsql_connection_name}"
            )
        elif db_user and db_password and db_name and db_host:
            database_url = f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:5432/{db_name}"
        else:
            database_url = f"sqlite:///{data_root / 'personal_finance.db'}"

    return WebSettings(
        app_name="Personal Finance Ledger",
        secret_key=os.environ.get("APP_SECRET_KEY", "change-me-before-production"),
        database_url=database_url,
        google_client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        finance_root=Path(os.environ.get("FINANCE_ROOT", str(PROJECT_ROOT / "sample-finance-data"))),
        preview_root=preview_root,
        upload_root=upload_root,
        allow_dev_login=os.environ.get("ALLOW_DEV_LOGIN", "0") == "1",
        allowed_google_email=os.environ.get("ALLOWED_GOOGLE_EMAIL", "").strip().lower(),
        public_base_url=os.environ.get("PUBLIC_BASE_URL", "").rstrip("/"),
    )
