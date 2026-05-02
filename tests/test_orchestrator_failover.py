import unittest

import requests

from local_proxy.upstream.orchestrator import request_upstream_with_retries


class NullLogger:
    def warning(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


def make_response(status_code: int, body: str, url: str) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = body.encode("utf-8")
    response.url = url
    response.headers["Content-Type"] = "text/html" if body.startswith("<html") else "application/json"
    return response


class GatewayFailoverTests(unittest.TestCase):
    def test_html_504_switches_to_next_healthy_route_before_key_rotation(self):
        sent_urls = []

        def sender(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if url == "https://bad.example/v1/chat/completions":
                return make_response(
                    504,
                    "<html><head><title>504 Gateway Time-out</title></head><body></body></html>",
                    url,
                )
            return make_response(200, '{"ok":true}', url)

        response, attempts, error = request_upstream_with_retries(
            {"method": "POST", "url": "https://bad.example/v1/chat/completions", "json": {"model": "demo"}},
            subpath="chat/completions",
            request_id="test-504",
            upstream_urls=[
                "https://bad.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
            model_candidates=["demo"],
            should_retry_request=lambda subpath, method: True,
            max_retries=3,
            should_enforce_route_switch_window=lambda urls, retry_allowed: True,
            route_switch_window_seconds=30,
            build_attempt_url_cycle=lambda urls, blocked: [url for url in urls if url not in blocked],
            build_model_candidate_order_for_route=lambda route, models, kwargs, request_id: {"candidates": models},
            should_race_model_candidates_for_route=lambda **kwargs: False,
            get_api_keys_for_url=lambda url: ["key-a", "key-b"],
            choose_api_key_for_url=lambda url, exclude=None: {
                "key": "key-a",
                "from_pool": True,
                "pool_name": "pool",
                "key_index": 0,
                "key_count": 2,
                "key_id": "key-a",
            },
            mark_api_key_success=lambda url, key: None,
            mark_api_key_failure=lambda url, key, reason, force_cooldown=False: None,
            mark_route_success=lambda url: None,
            mark_route_failure=lambda url, reason: None,
            response_indicates_model_unavailable=lambda response: False,
            classify_upstream_response=lambda response: (
                ("switch_route", f"route_switch_{response.status_code}")
                if response.status_code in {502, 503, 504}
                else ("return", f"status_{response.status_code}")
            ),
            extract_error_preview_from_response=lambda response: response.text[:120],
            apply_model_candidate_to_request_kwargs=lambda kwargs, model: dict(kwargs),
            apply_learned_completion_limit_to_request_kwargs=lambda *args, **kwargs: 0,
            extract_completion_token_limit_from_response=lambda response: None,
            extract_context_token_limit_from_response=lambda response: (None, None),
            clamp_payload_output_tokens=lambda payload, limit: 0,
            record_learned_model_capability=lambda **kwargs: None,
            record_model_candidate_result=lambda **kwargs: None,
            compute_retry_delay_ms=lambda attempt, response=None: 0,
            remaining_retry_window_ms=lambda deadline: 30000,
            append_race_attempts=lambda attempts, race_attempts, **kwargs: set(),
            model_candidate_differs_from_logical=lambda logical, candidate: False,
            logger=NullLogger(),
            cache_stat_bump=lambda key: None,
            model_candidate_race_limit=1,
            model_candidate_race_timeout_seconds=1,
            enable_model_candidate_race=False,
            request_sender=sender,
        )

        self.assertIsNone(error)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sent_urls,
            [
                "https://bad.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
        )
        self.assertEqual(attempts[0]["status_code"], 504)
        self.assertEqual(attempts[0]["action"], "switch_route")


if __name__ == "__main__":
    unittest.main()
