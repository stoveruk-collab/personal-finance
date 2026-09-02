from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Sequence

import httpx

from ..settings import load_web_settings


logger = logging.getLogger(__name__)

CATEGORY_BATCH_SIZE = 100
CATEGORY_REQUEST_TIMEOUT_SECONDS = 20.0
CATEGORY_TOTAL_TIMEOUT_SECONDS = 25.0
CATEGORY_MAX_CONCURRENCY = 4


@dataclass(frozen=True)
class CategoryGuess:
    category_name: str | None
    reason: str
    model: str


async def guess_categories(category_names: Sequence[str], raw_texts: Sequence[str]) -> list[CategoryGuess]:
    """Classify transaction text in bounded batches while preserving input order."""
    if not raw_texts:
        return []

    settings = load_web_settings()
    if not settings.openai_api_key:
        return [CategoryGuess(None, "No OpenAI API key configured.", "") for _ in raw_texts]
    if not category_names:
        return [CategoryGuess(None, "No active categories are configured.", "") for _ in raw_texts]

    unique_texts = list(dict.fromkeys(raw_texts))
    batches = [
        unique_texts[index : index + CATEGORY_BATCH_SIZE]
        for index in range(0, len(unique_texts), CATEGORY_BATCH_SIZE)
    ]
    semaphore = asyncio.Semaphore(CATEGORY_MAX_CONCURRENCY)
    timeout = httpx.Timeout(CATEGORY_REQUEST_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [
            asyncio.create_task(
                _guess_category_batch(
                    client,
                    semaphore,
                    category_names=list(category_names),
                    raw_texts=batch,
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                )
            )
            for batch in batches
        ]
        done, pending = await asyncio.wait(tasks, timeout=CATEGORY_TOTAL_TIMEOUT_SECONDS)
        if pending:
            logger.warning(
                "OpenAI categorization reached its %.0f-second total time limit; skipping %s batches",
                CATEGORY_TOTAL_TIMEOUT_SECONDS,
                len(pending),
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        batch_results = []
        for task, batch in zip(tasks, batches):
            if task not in done:
                batch_results.append([_unavailable_guess(settings.openai_model) for _ in batch])
                continue
            try:
                batch_results.append(task.result())
            except Exception as exc:
                logger.warning("OpenAI category batch failed unexpectedly: %s", type(exc).__name__)
                batch_results.append([_unavailable_guess(settings.openai_model) for _ in batch])

    guesses_by_text: dict[str, CategoryGuess] = {}
    for batch, guesses in zip(batches, batch_results):
        guesses_by_text.update(zip(batch, guesses))
    return [guesses_by_text[text] for text in raw_texts]


async def _guess_category_batch(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    *,
    category_names: list[str],
    raw_texts: list[str],
    api_key: str,
    model: str,
) -> list[CategoryGuess]:
    request_rows = [
        {"index": index, "transaction_text": raw_text}
        for index, raw_text in enumerate(raw_texts)
    ]
    prompt = {
        "transactions": request_rows,
        "categories": category_names,
        "instruction": (
            "Choose the single best category for every household finance transaction. "
            "Return one classification for every input index and use only a category from the list."
        ),
    }
    body = {
        "model": model,
        "store": False,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "You classify consumer finance transactions into an existing category list.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(prompt)}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "transaction_categories",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "classifications": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "index": {"type": "integer"},
                                    "category": {"type": "string", "enum": category_names},
                                    "reason": {"type": "string"},
                                },
                                "required": ["index", "category", "reason"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["classifications"],
                    "additionalProperties": False,
                },
            }
        },
        "max_output_tokens": min(32768, max(1000, len(raw_texts) * 120)),
    }

    try:
        async with semaphore:
            response = await asyncio.wait_for(
                client.post(
                    "https://api.openai.com/v1/responses",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                ),
                timeout=CATEGORY_REQUEST_TIMEOUT_SECONDS,
            )
        response.raise_for_status()
        payload = response.json()
        parsed = json.loads(_response_text(payload))
        raw_classifications = parsed.get("classifications", [])
    except (asyncio.TimeoutError, httpx.HTTPError, json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
        logger.warning(
            "OpenAI category batch failed for %s transaction descriptions: %s",
            len(raw_texts),
            type(exc).__name__,
        )
        return [_unavailable_guess(model) for _ in raw_texts]

    guesses_by_index: dict[int, CategoryGuess] = {}
    allowed_categories = set(category_names)
    for item in raw_classifications:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        category_name = item.get("category")
        reason = item.get("reason")
        if (
            isinstance(index, int)
            and 0 <= index < len(raw_texts)
            and category_name in allowed_categories
            and isinstance(reason, str)
        ):
            guesses_by_index[index] = CategoryGuess(category_name, reason, model)

    if len(guesses_by_index) != len(raw_texts):
        logger.warning(
            "OpenAI category batch returned %s valid classifications for %s transaction descriptions",
            len(guesses_by_index),
            len(raw_texts),
        )
    return [guesses_by_index.get(index, _unavailable_guess(model)) for index in range(len(raw_texts))]


def _response_text(payload: dict) -> str:
    text = payload.get("output_text", "")
    if text:
        return text
    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def _unavailable_guess(model: str) -> CategoryGuess:
    return CategoryGuess(
        None,
        "AI categorization was unavailable; choose a category manually.",
        model,
    )
