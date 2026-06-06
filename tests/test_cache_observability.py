import unittest

from local_proxy.compat.protocols import build_openai_usage_from_response
from local_proxy.runtime.prompt_cache import build_prompt_prefix_observability
from local_proxy.server import build_usage_observability_meta


class CacheObservabilityTests(unittest.TestCase):
    def test_openrouter_cache_write_tokens_map_to_creation_tokens(self):
        usage = build_openai_usage_from_response(
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 5,
                    "total_tokens": 105,
                    "prompt_tokens_details": {
                        "cached_tokens": 40,
                        "cache_write_tokens": 60,
                    },
                },
            }
        )

        self.assertEqual(usage["cache_read_input_tokens"], 40)
        self.assertEqual(usage["cache_creation_input_tokens"], 60)
        self.assertEqual(usage["prompt_tokens_details"]["cached_tokens"], 40)
        self.assertEqual(usage["prompt_tokens_details"]["cache_creation_tokens"], 60)

    def test_gemini_usage_metadata_maps_cached_content_tokens(self):
        meta = build_usage_observability_meta(
            {
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "candidatesTokenCount": 7,
                    "totalTokenCount": 107,
                    "cachedContentTokenCount": 55,
                }
            }
        )

        self.assertEqual(meta["prompt_tokens"], 100)
        self.assertEqual(meta["completion_tokens"], 7)
        self.assertEqual(meta["total_tokens"], 107)
        self.assertEqual(meta["cache_read_input_tokens"], 55)
        self.assertEqual(meta["prompt_cache_hit_tokens"], 55)

    def test_prompt_prefix_observability_is_stable_for_tool_order(self):
        payload_a = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": " rules\n"},
                {"role": "user", "content": "hello"},
            ],
            "tools": [
                {"type": "function", "function": {"name": "Write", "parameters": {"type": "object"}}},
                {"type": "function", "function": {"name": "Read", "parameters": {"type": "object"}}},
            ],
        }
        payload_b = {
            **payload_a,
            "tools": list(reversed(payload_a["tools"])),
        }

        meta_a = build_prompt_prefix_observability(payload_a)
        meta_b = build_prompt_prefix_observability(payload_b)

        self.assertEqual(meta_a["prompt_prefix_hash"], meta_b["prompt_prefix_hash"])
        self.assertEqual(meta_a["prompt_tool_count"], 2)


if __name__ == "__main__":
    unittest.main()
