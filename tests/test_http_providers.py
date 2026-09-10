import unittest
from unittest.mock import patch

from sfc.http_providers import GeminiProvider
from sfc.providers import ProviderRequest


class HttpProviderTests(unittest.TestCase):
    @patch("sfc.http_providers._post")
    def test_gemini_receives_function_declarations_and_returns_call(self, post) -> None:
        post.return_value = {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "element.get", "args": {"elementId": "P-1"}}}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4},
        }
        response = GeminiProvider("test-key").complete(ProviderRequest(
            "inspect the panel",
            tools=(
                {"name": "element.get", "description": "Get an element", "input_schema": {"type": "object", "properties": {"elementId": {"type": "string"}}}},
            ),
        ))

        payload = post.call_args.args[2]
        declaration = payload["tools"][0]["function_declarations"][0]
        self.assertEqual(declaration["name"], "element.get")
        self.assertEqual(declaration["parameters"]["properties"]["elementId"]["type"], "string")
        self.assertEqual(response.tool_calls[0].name, "element.get")
        self.assertEqual(response.tool_calls[0].arguments["elementId"], "P-1")


if __name__ == "__main__":
    unittest.main()
