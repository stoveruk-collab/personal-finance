from __future__ import annotations

import json
import urllib.error
import urllib.request

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Category
from ..settings import load_web_settings


def guess_category(db: Session, raw_text: str) -> tuple[str | None, str, str]:
    settings = load_web_settings()
    if not settings.openai_api_key:
        return None, "No OpenAI API key configured.", ""

    categories = db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.name)).all()
    category_names = [item.name for item in categories]
    prompt = {
        "transaction_text": raw_text,
        "categories": category_names,
        "instruction": (
            "Choose the single best category for this household finance transaction. "
            "Return JSON with keys category and reason. Use only one category from the list."
        ),
    }
    body = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "You classify consumer finance transactions into an existing category list. Return valid JSON only.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(prompt)}],
            },
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return None, f"OpenAI request failed: {exc}", settings.openai_model

    text = payload.get("output_text", "")
    if not text:
        output_items = payload.get("output", []) or []
        chunks: list[str] = []
        for item in output_items:
            for content in item.get("content", []) or []:
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(content["text"])
        text = "\n".join(chunks).strip()
    if not text:
        return None, "OpenAI returned no category text.", settings.openai_model

    try:
        parsed = json.loads(_extract_json(text))
    except json.JSONDecodeError:
        return None, text[:500], settings.openai_model

    category_name = parsed.get("category")
    reason = parsed.get("reason", "")
    if category_name not in category_names:
        return None, reason or f"Suggested category {category_name!r} is not in the active list.", settings.openai_model
    return category_name, reason, settings.openai_model


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]
