import json
import os
import unittest
from unittest.mock import patch

from app.extraction_service import extract_with_provider


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class LLMProviderTests(unittest.TestCase):
    def test_extract_with_gemini_uses_configured_model(self):
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps({"vendor_name": "Example Co"})}]
                    }
                }
            ]
        }

        def fake_urlopen(request, timeout=60):
            self.assertIn("gemini-1.5-flash", request.full_url)
            return FakeResponse(payload)

        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-1.5-flash"}, clear=False):
            with patch("app.extraction_service.urllib.request.urlopen", side_effect=fake_urlopen):
                result = extract_with_provider("Invoice text", "gemini", api_key="test-key")

        self.assertEqual(result["vendor_name"], "Example Co")

    def test_extract_with_gemini_parses_structured_json(self):
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "vendor_name": "Example Co",
                                        "invoice_number": "1001",
                                        "invoice_date": "2024-03-15",
                                        "line_items": [
                                            {
                                                "description": "Consulting",
                                                "quantity": 2,
                                                "unit_price": 100.0,
                                                "amount": 200.0,
                                            }
                                        ],
                                        "subtotal": 200.0,
                                        "tax": 20.0,
                                        "total": 220.0,
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }

        with patch("app.extraction_service.urllib.request.urlopen", return_value=FakeResponse(payload)):
            result = extract_with_provider("Invoice text", "gemini", api_key="test-key")

        self.assertEqual(result["vendor_name"], "Example Co")
        self.assertEqual(result["line_items"][0]["description"], "Consulting")
        self.assertEqual(result["total"], 220.0)


if __name__ == "__main__":
    unittest.main()
