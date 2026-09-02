from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from personal_finance.web.services.categorizer import guess_categories


def api_response(classifications: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"output_text": json.dumps({"classifications": classifications})},
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )


class CategoryBatchingTest(unittest.IsolatedAsyncioTestCase):
    def settings(self):
        return SimpleNamespace(openai_api_key="test-key", openai_model="gpt-4.1-mini")

    async def test_classifies_unique_descriptions_in_one_structured_request(self):
        response = api_response(
            [
                {"index": 0, "category": "Groceries", "reason": "A food shop."},
                {"index": 1, "category": "Dining", "reason": "A restaurant."},
            ]
        )
        with (
            patch(
                "personal_finance.web.services.categorizer.load_web_settings",
                return_value=self.settings(),
            ),
            patch(
                "personal_finance.web.services.categorizer.httpx.AsyncClient.post",
                new=AsyncMock(return_value=response),
            ) as post,
        ):
            guesses = await guess_categories(
                ["Groceries", "Dining"],
                ["Corner Shop", "Pizza Place", "Corner Shop"],
            )

        self.assertEqual([guess.category_name for guess in guesses], ["Groceries", "Dining", "Groceries"])
        self.assertEqual(post.await_count, 1)
        body = post.await_args.kwargs["json"]
        prompt = json.loads(body["input"][1]["content"][0]["text"])
        self.assertEqual(len(prompt["transactions"]), 2)
        self.assertFalse(body["store"])
        self.assertEqual(body["text"]["format"]["type"], "json_schema")

    async def test_missing_classification_falls_back_without_failing_preview(self):
        response = api_response(
            [{"index": 0, "category": "Groceries", "reason": "A food shop."}]
        )
        with (
            patch(
                "personal_finance.web.services.categorizer.load_web_settings",
                return_value=self.settings(),
            ),
            patch(
                "personal_finance.web.services.categorizer.httpx.AsyncClient.post",
                new=AsyncMock(return_value=response),
            ),
        ):
            guesses = await guess_categories(
                ["Groceries", "Dining"],
                ["Corner Shop", "Unknown Merchant"],
            )

        self.assertEqual(guesses[0].category_name, "Groceries")
        self.assertIsNone(guesses[1].category_name)
        self.assertIn("choose a category manually", guesses[1].reason)

    async def test_api_timeout_falls_back_without_failing_preview(self):
        with (
            patch(
                "personal_finance.web.services.categorizer.load_web_settings",
                return_value=self.settings(),
            ),
            patch(
                "personal_finance.web.services.categorizer.httpx.AsyncClient.post",
                new=AsyncMock(side_effect=httpx.ReadTimeout("slow response")),
            ),
        ):
            guesses = await guess_categories(["Groceries"], ["Unknown Merchant"])

        self.assertIsNone(guesses[0].category_name)
        self.assertEqual(guesses[0].model, "gpt-4.1-mini")
        self.assertIn("choose a category manually", guesses[0].reason)

    async def test_large_inputs_are_split_into_concurrent_batches(self):
        async def classify_request(url, **kwargs):
            body = kwargs["json"]
            prompt = json.loads(body["input"][1]["content"][0]["text"])
            return api_response(
                [
                    {"index": row["index"], "category": "Groceries", "reason": "Test result."}
                    for row in prompt["transactions"]
                ]
            )

        with (
            patch(
                "personal_finance.web.services.categorizer.load_web_settings",
                return_value=self.settings(),
            ),
            patch("personal_finance.web.services.categorizer.CATEGORY_BATCH_SIZE", 2),
            patch(
                "personal_finance.web.services.categorizer.httpx.AsyncClient.post",
                new=AsyncMock(side_effect=classify_request),
            ) as post,
        ):
            guesses = await guess_categories(
                ["Groceries"],
                ["Merchant One", "Merchant Two", "Merchant Three"],
            )

        self.assertEqual(post.await_count, 2)
        self.assertEqual([guess.category_name for guess in guesses], ["Groceries"] * 3)

    async def test_total_time_limit_cancels_slow_batches(self):
        async def slow_post(*args, **kwargs):
            await asyncio.sleep(1)
            return api_response([])

        with (
            patch(
                "personal_finance.web.services.categorizer.load_web_settings",
                return_value=self.settings(),
            ),
            patch(
                "personal_finance.web.services.categorizer.CATEGORY_TOTAL_TIMEOUT_SECONDS",
                0.01,
            ),
            patch(
                "personal_finance.web.services.categorizer.httpx.AsyncClient.post",
                new=AsyncMock(side_effect=slow_post),
            ),
        ):
            guesses = await guess_categories(["Groceries"], ["Unknown Merchant"])

        self.assertIsNone(guesses[0].category_name)
        self.assertIn("choose a category manually", guesses[0].reason)


if __name__ == "__main__":
    unittest.main()
