from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import uvicorn
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from .db import Base, SessionLocal, engine, get_db
from .models import Account, BudgetSetting, Category, HistoricalReport, ImportBatch, ImportPreview, MappingRule, Transaction, User
from .parsing import build_fingerprint, existing_occurrence_count, parse_uploaded_file, transaction_to_dict
from .reports import annual_report_data, available_years, budget_settings, close_year, format_gbp, month_name, month_options, monthly_report_data
from .seed import seed_defaults
from .services.categorizer import guess_category
from .settings import load_web_settings


settings = load_web_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")

oauth = OAuth()
if settings.google_client_id and settings.google_client_secret:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def build_google_redirect_uri(request: Request) -> str:
    if settings.public_base_url:
        return f"{settings.public_base_url}/auth/google"
    return str(request.url_for("auth_google"))


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


def get_current_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def store_preview(db: Session, payload: dict) -> str:
    preview_id = uuid.uuid4().hex
    db.merge(ImportPreview(id=preview_id, payload=json.dumps(payload)))
    db.commit()
    return preview_id


def load_preview(db: Session, preview_id: str) -> dict:
    record = db.get(ImportPreview, preview_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Preview not found.")
    return json.loads(record.payload)


def delete_preview(db: Session, preview_id: str) -> None:
    record = db.get(ImportPreview, preview_id)
    if record is not None:
        db.delete(record)
        db.commit()


def render_monthly_report_html(request: Request, report: dict) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="monthly_report.html",
        context={"request": request, "report": report, "format_gbp": format_gbp},
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    account_count = db.scalar(select(func.count()).select_from(Account)) or 0
    transaction_count = db.scalar(select(func.count()).select_from(Transaction)) or 0
    open_years = sorted(set(db.scalars(select(Transaction.year)).all()), reverse=True)
    now = datetime.now(ZoneInfo("Europe/London"))
    current_year = now.year
    current_month = now.month
    current_month_label = f"{month_name(current_year, current_month)} {current_year}"
    current_report = monthly_report_data(db, current_year, current_month)
    budget_lookup = {
        budget.category.name: Decimal(str(budget.monthly_budget))
        for budget in budget_settings(db)
        if budget.category is not None
    }
    actual_lookup = {section["category"]: section["amount"] for section in current_report["expense_sections"]}
    watched_categories = [
        "Groceries & Supplies",
        "Dining & Food Delivery",
        "Discretionary Retail",
    ]
    watch_rows = []
    for category_name in watched_categories:
        actual = actual_lookup.get(category_name, Decimal("0"))
        budget = budget_lookup.get(category_name, Decimal("0"))
        watch_rows.append(
            {
                "category": category_name,
                "actual": actual,
                "budget": budget,
            }
        )

    def build_chart_row(category_name: str, actual: Decimal, budget: Decimal) -> dict:
        scale_value = max(actual, budget, Decimal("1"))
        budget_width = (budget / scale_value) * Decimal("100") if budget > 0 else Decimal("0")
        actual_width = (actual / scale_value) * Decimal("100") if actual > 0 else Decimal("0")
        percent_of_budget = ((actual / budget) * Decimal("100")) if budget > 0 else Decimal("0")
        return {
            "category": category_name,
            "actual": actual,
            "budget": budget,
            "variance": budget - actual,
            "budget_width": float(budget_width),
            "actual_width": float(actual_width),
            "percent_of_budget": float(percent_of_budget),
            "is_over_budget": actual > budget if budget > 0 else actual > 0,
        }

    overall_chart_row = build_chart_row(
        "Overall",
        current_report["total_expenses"],
        current_report["total_budget"],
    )

    chart_rows = []
    for category_name in sorted(set(actual_lookup) | set(budget_lookup)):
        actual = actual_lookup.get(category_name, Decimal("0"))
        budget = budget_lookup.get(category_name, Decimal("0"))
        if actual == 0 and budget == 0:
            continue
        chart_rows.append(build_chart_row(category_name, actual, budget))
    auth_warning = None
    if not settings.allow_dev_login and not (settings.google_client_id and settings.google_client_secret):
        auth_warning = (
            "Google OAuth is not configured yet. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, "
            f"and ALLOWED_GOOGLE_EMAIL={settings.allowed_google_email} before using this app without development login."
        )
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "user": user,
            "account_count": account_count,
            "transaction_count": transaction_count,
            "open_years": open_years,
            "auth_warning": auth_warning,
            "format_gbp": format_gbp,
            "current_month_label": current_month_label,
            "watch_rows": watch_rows,
            "overall_chart_row": overall_chart_row,
            "chart_rows": chart_rows,
            "current_report": current_report,
        },
    )


@app.get("/reports", response_class=HTMLResponse)
def reports_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    period: str = Query(default="month"),
    year: Optional[int] = Query(default=None),
    month: Optional[int] = Query(default=None),
):
    month_choices = month_options(db)
    year_choices = available_years(db)
    default_month = month_choices[0] if month_choices else None
    selected_year = year or (default_month["year"] if default_month else (year_choices[0] if year_choices else datetime.utcnow().year))
    selected_month = month or (default_month["month"] if default_month else datetime.utcnow().month)
    if period == "year":
        report = annual_report_data(db, selected_year)
    else:
        report = monthly_report_data(db, selected_year, selected_month)
    return templates.TemplateResponse(
        request=request,
        name="reports_dashboard.html",
        context={
            "request": request,
            "user": user,
            "period": period,
            "selected_year": selected_year,
            "selected_month": selected_month,
            "month_choices": month_choices,
            "year_choices": year_choices,
            "report": report,
            "format_gbp": format_gbp,
        },
    )


@app.get("/healthz")
def healthcheck():
    return {"status": "ok", "app": settings.app_name}


@app.get("/login")
async def login(request: Request):
    if settings.allow_dev_login:
        return HTMLResponse("<a href='/login/dev'>Sign in with development login</a>")
    if not (settings.google_client_id and settings.google_client_secret):
        return HTMLResponse("Google OAuth is not configured yet. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", status_code=500)
    redirect_uri = build_google_redirect_uri(request)
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/login/dev")
def login_dev(request: Request, db: Session = Depends(get_db)):
    if not settings.allow_dev_login:
        raise HTTPException(status_code=404)
    user = db.scalar(select(User).where(User.email == "dev@example.com"))
    if user is None:
        user = User(email="dev@example.com", name="Development User", google_sub="dev-user")
        db.add(user)
        db.commit()
        db.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/auth/google")
async def auth_google(request: Request, db: Session = Depends(get_db)):
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(status_code=500, detail="Google OAuth is not configured.")
    token = await oauth.google.authorize_access_token(request)
    user_info = token["userinfo"]
    email = user_info["email"].strip().lower()
    if email != settings.allowed_google_email:
        request.session.clear()
        return HTMLResponse(
            f"Access denied. This app only allows Google sign-in for {settings.allowed_google_email}.",
            status_code=403,
        )
    user = db.scalar(select(User).where(User.google_sub == user_info["sub"]))
    if user is None:
        user = User(email=email, name=user_info.get("name", email), google_sub=user_info["sub"])
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email = email
        user.name = user_info.get("name", email)
        db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.get("/imports/new", response_class=HTMLResponse)
def import_form(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(
        request=request,
        name="import_upload.html",
        context={"request": request, "user": user},
    )


@app.post("/imports/preview", response_class=HTMLResponse)
async def import_preview(request: Request, files: list[UploadFile] = File(...), db: Session = Depends(get_db), user: User = Depends(require_user)):
    categories = db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.name)).all()
    rows: list[dict] = []
    duplicate_count = 0
    seen_signature_counts: dict[str, int] = {}

    upload_dir = settings.upload_root / uuid.uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)

    for uploaded in files:
        target = upload_dir / uploaded.filename
        target.write_bytes(await uploaded.read())
        for item in parse_uploaded_file(target, db):
            occurrence_index = seen_signature_counts.get(item.dedupe_signature, 0) + 1
            seen_signature_counts[item.dedupe_signature] = occurrence_index
            existing_count = existing_occurrence_count(
                db,
                account_name=item.account_name,
                posted_at=item.posted_at,
                amount=item.amount,
                payee=item.payee,
                memo=item.memo,
            )
            if occurrence_index <= existing_count:
                duplicate_count += 1
                continue
            chosen_category = item.category_name
            ai_reason = ""
            ai_model = ""
            if chosen_category is None:
                chosen_category, ai_reason, ai_model = guess_category(db, item.raw_text)
            rows.append(
                {
                    **transaction_to_dict(item),
                    "selected_category_name": chosen_category or "",
                    "ai_guess_reason": ai_reason,
                    "ai_guess_model": ai_model,
                    "default_rule_pattern": item.payee or item.raw_text,
                    "occurrence_index": occurrence_index,
                    "fingerprint": build_fingerprint(item.dedupe_signature, occurrence_index),
                }
            )

    preview_id = store_preview(db, {"rows": rows, "uploaded_files": [file.filename for file in files], "upload_dir": str(upload_dir)})
    return templates.TemplateResponse(
        request=request,
        name="import_preview.html",
        context={
            "request": request,
            "user": user,
            "preview_id": preview_id,
            "rows": rows,
            "categories": categories,
            "duplicate_count": duplicate_count,
        },
    )


@app.post("/imports/commit")
async def import_commit(request: Request, preview_id: str = Form(...), db: Session = Depends(get_db), user: User = Depends(require_user)):
    payload = load_preview(db, preview_id)
    rows = payload["rows"]

    batch = ImportBatch(uploaded_files=", ".join(payload["uploaded_files"]), imported_by_user_id=user.id, notes="")
    db.add(batch)
    db.flush()

    category_lookup = {category.name: category for category in db.scalars(select(Category)).all()}
    account_lookup = {account.name: account for account in db.scalars(select(Account)).all()}

    form = await request.form()
    imported_count = 0

    for index, row in enumerate(rows):
        category_name = form.get(f"category_{index}", row["selected_category_name"])
        account_name = row["account_name"]
        account = account_lookup.get(account_name)
        if account is None:
            account = Account(name=account_name, slug=account_name.lower().replace(" ", "-"))
            db.add(account)
            db.flush()
            account_lookup[account_name] = account
        category = category_lookup.get(category_name) if category_name else None
        tx = Transaction(
            fingerprint=row["fingerprint"],
            year=datetime.fromisoformat(row["posted_at"]).year,
            posted_at=datetime.fromisoformat(row["posted_at"]),
            amount=Decimal(row["amount"]),
            payee=row["payee"],
            memo=row["memo"],
            raw_text=row["raw_text"],
            source_file=row["source_file"],
            source_account_label=row["account_name"],
            matched_by=row["matched_by"],
            mapping_source=row["mapping_source"],
            review_note=row["review_note"],
            ai_guess_reason=row["ai_guess_reason"],
            ai_guess_model=row["ai_guess_model"],
            account_id=account.id,
            category_id=category.id if category else None,
            import_batch_id=batch.id,
        )
        db.add(tx)
        imported_count += 1

        save_rule = form.get(f"save_rule_{index}") == "on"
        rule_pattern = (form.get(f"rule_pattern_{index}") or "").strip()
        rule_match_type = (form.get(f"rule_match_type_{index}") or "contains").strip().lower()
        if save_rule and category and rule_pattern:
            existing_rule = db.scalar(
                select(MappingRule).where(
                    MappingRule.pattern == rule_pattern,
                    MappingRule.match_type == rule_match_type,
                    MappingRule.category_id == category.id,
                )
            )
            if existing_rule is None:
                db.add(
                    MappingRule(
                        priority=1000,
                        match_type=rule_match_type,
                        pattern=rule_pattern,
                        category_id=category.id,
                    )
                )

    db.commit()
    delete_preview(db, preview_id)
    return RedirectResponse(f"/imports/{batch.id}?imported={imported_count}", status_code=303)


@app.get("/imports/{batch_id}", response_class=HTMLResponse)
def import_result(batch_id: int, request: Request, imported: int = 0, db: Session = Depends(get_db), user: User = Depends(require_user)):
    batch = db.get(ImportBatch, batch_id)
    txs = db.scalars(
        select(Transaction)
        .options(joinedload(Transaction.account), joinedload(Transaction.category))
        .where(Transaction.import_batch_id == batch_id)
        .order_by(Transaction.posted_at, Transaction.id)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="import_result.html",
        context={"request": request, "user": user, "batch": batch, "transactions": txs, "imported": imported, "format_gbp": format_gbp},
    )


@app.get("/reports/monthly/{year}/{month}", response_class=HTMLResponse)
def monthly_report(year: int, month: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return RedirectResponse(f"/reports?period=month&year={year}&month={month}", status_code=303)


@app.get("/reports/history/{report_id}", response_class=HTMLResponse)
def historical_report(report_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    report = db.get(HistoricalReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Historical report not found.")
    return HTMLResponse(report.html)


@app.get("/ledger", response_class=HTMLResponse)
def ledger(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    account_id: Optional[str] = Query(default=None),
    month: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
):
    parsed_account_id: Optional[int] = None
    if account_id not in (None, ""):
        try:
            parsed_account_id = int(account_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="account_id must be an integer when provided.") from exc
    month_start: Optional[datetime] = None
    next_month_start: Optional[datetime] = None
    if month not in (None, ""):
        try:
            month_start = datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="month must be in YYYY-MM format when provided.") from exc
        if month_start.month == 12:
            next_month_start = datetime(month_start.year + 1, 1, 1)
        else:
            next_month_start = datetime(month_start.year, month_start.month + 1, 1)
    search_text = (search or "").strip()
    query = select(Transaction).options(joinedload(Transaction.account), joinedload(Transaction.category)).order_by(Transaction.posted_at.desc(), Transaction.id.desc())
    if parsed_account_id is not None:
        query = query.where(Transaction.account_id == parsed_account_id)
    if month_start is not None and next_month_start is not None:
        query = query.where(Transaction.posted_at >= month_start, Transaction.posted_at < next_month_start)
    if search_text:
        pattern = f"%{search_text}%"
        query = query.where(
            or_(
                Transaction.payee.ilike(pattern),
                Transaction.memo.ilike(pattern),
                Transaction.raw_text.ilike(pattern),
            )
        )
    transactions = db.scalars(query.limit(500)).all()
    accounts = db.scalars(select(Account).order_by(Account.name)).all()
    categories = db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.name)).all()
    month_values = []
    seen_months: set[str] = set()
    for posted_at in db.scalars(select(Transaction.posted_at).order_by(Transaction.posted_at.desc())).all():
        month_value = posted_at.strftime("%Y-%m")
        if month_value in seen_months:
            continue
        seen_months.add(month_value)
        month_values.append(
            {
                "value": month_value,
                "label": posted_at.strftime("%B %Y"),
            }
        )
    return templates.TemplateResponse(
        request=request,
        name="ledger.html",
        context={
            "request": request,
            "user": user,
            "transactions": transactions,
            "accounts": accounts,
            "categories": categories,
            "month_values": month_values,
            "selected_account_id": parsed_account_id,
            "selected_month": month or "",
            "search": search_text,
            "format_gbp": format_gbp,
        },
    )


@app.post("/ledger/transactions/{transaction_id}")
async def update_ledger_transaction(
    transaction_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    form = await request.form()
    category_id_raw = (form.get("category_id") or "").strip()
    account_id = (form.get("account_id") or "").strip()
    month = (form.get("month") or "").strip()
    search = (form.get("search") or "").strip()

    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    category = None
    if category_id_raw:
        try:
            category_id = int(category_id_raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="category_id must be an integer when provided.") from exc
        category = db.get(Category, category_id)
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found.")

    transaction.category_id = category.id if category else None
    db.commit()

    query_parts = []
    if account_id:
        query_parts.append(f"account_id={account_id}")
    if month:
        query_parts.append(f"month={month}")
    if search:
        query_parts.append(f"search={search}")
    query_string = f"?{'&'.join(query_parts)}" if query_parts else ""
    return RedirectResponse(f"/ledger{query_string}", status_code=303)


@app.get("/accounts/{account_id}/ledger", response_class=HTMLResponse)
def account_ledger(account_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return ledger(request=request, db=db, user=user, account_id=account_id)


@app.get("/categories", response_class=HTMLResponse)
def categories(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    categories = db.scalars(select(Category).order_by(Category.name)).all()
    return templates.TemplateResponse(
        request=request,
        name="categories.html",
        context={"request": request, "user": user, "categories": categories},
    )


@app.post("/categories")
def create_category(name: str = Form(...), db: Session = Depends(get_db), user: User = Depends(require_user)):
    cleaned = name.strip()
    if cleaned:
        category = Category(name=cleaned, is_active=True)
        db.add(category)
        db.commit()
    return RedirectResponse("/categories", status_code=303)


@app.get("/mappings", response_class=HTMLResponse)
def mappings(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    rules = db.scalars(
        select(MappingRule)
        .options(joinedload(MappingRule.category))
        .order_by(MappingRule.priority.desc(), MappingRule.pattern.asc())
    ).all()
    categories = db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.name)).all()
    return templates.TemplateResponse(
        request=request,
        name="mappings.html",
        context={"request": request, "user": user, "rules": rules, "categories": categories},
    )


@app.post("/mappings")
def create_mapping(
    pattern: str = Form(...),
    match_type: str = Form(...),
    category_id: int = Form(...),
    priority: int = Form(1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    db.add(MappingRule(priority=priority, match_type=match_type.strip().lower(), pattern=pattern.strip(), category_id=category_id))
    db.commit()
    return RedirectResponse("/mappings", status_code=303)


@app.post("/mappings/{rule_id}")
def update_mapping(
    rule_id: int,
    pattern: str = Form(...),
    match_type: str = Form(...),
    category_id: int = Form(...),
    priority: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    rule = db.get(MappingRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Mapping rule not found.")
    rule.pattern = pattern.strip()
    rule.match_type = match_type.strip().lower()
    rule.category_id = category_id
    rule.priority = priority
    db.commit()
    return RedirectResponse("/mappings", status_code=303)


@app.post("/categories/{category_id}")
def update_category(category_id: int, name: str = Form(...), is_active: Optional[str] = Form(None), db: Session = Depends(get_db), user: User = Depends(require_user)):
    category = db.get(Category, category_id)
    category.name = name.strip()
    category.is_active = is_active == "on"
    db.commit()
    return RedirectResponse("/categories", status_code=303)


@app.post("/budgets")
async def update_budgets(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    records = db.scalars(select(BudgetSetting).options(joinedload(BudgetSetting.category))).all()
    by_id = {record.id: record for record in records}
    for key, value in form.multi_items():
        if not key.startswith("budget_"):
            continue
        budget_id = int(key.split("_", 1)[1])
        record = by_id.get(budget_id)
        if record is None:
            continue
        amount_text = str(value or "0").strip() or "0"
        record.monthly_budget = Decimal(amount_text)
    db.commit()

    redirect_period = str(form.get("period", "month"))
    redirect_year = str(form.get("year", "")).strip()
    redirect_month = str(form.get("month", "")).strip()
    target = f"/reports?period={redirect_period}"
    if redirect_year:
        target += f"&year={redirect_year}"
    if redirect_month:
        target += f"&month={redirect_month}"
    return RedirectResponse(target, status_code=303)


@app.get("/budgets", response_class=HTMLResponse)
def budgets_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request=request,
        name="budgets.html",
        context={
            "request": request,
            "user": user,
            "budgets": budget_settings(db),
            "format_gbp": format_gbp,
        },
    )


@app.get("/years/close", response_class=HTMLResponse)
def year_close_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    years = sorted({year for year in db.scalars(select(Transaction.year)).all()}, reverse=True)
    return templates.TemplateResponse(
        request=request,
        name="year_close.html",
        context={"request": request, "user": user, "years": years},
    )


@app.post("/years/close")
def year_close_submit(request: Request, year: int = Form(...), db: Session = Depends(get_db), user: User = Depends(require_user)):
    def render_html(report: dict) -> str:
        template = templates.get_template("monthly_report.html")
        return template.render({"request": request, "user": user, "report": report, "format_gbp": format_gbp})

    close_year(db, year, render_html)
    return RedirectResponse("/", status_code=303)


def run() -> None:
    uvicorn.run("personal_finance.web.app:app", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")), reload=True)
