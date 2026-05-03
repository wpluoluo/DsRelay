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
        key_failures = []
        route_failures = []

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
            mark_api_key_failure=lambda url, key, reason, force_cooldown=False: key_failures.append(
                (url, reason, force_cooldown)
            ),
            mark_route_success=lambda url: None,
            mark_route_failure=lambda url, reason: route_failures.append((url, reason)),
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
        self.assertEqual(route_failures, [])
        self.assertEqual(key_failures, [])

    def test_request_exception_switches_route_without_marking_failure(self):
        sent_urls = []
        key_failures = []
        route_failures = []

        def sender(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if url == "https://timeout.example/v1/chat/completions":
                raise requests.Timeout("connect timed out")
            return make_response(200, '{"ok":true}', url)

        response, attempts, error = request_upstream_with_retries(
            {"method": "POST", "url": "https://timeout.example/v1/chat/completions", "json": {"model": "demo"}},
            subpath="chat/completions",
            request_id="test-timeout",
            upstream_urls=[
                "https://timeout.example/v1/chat/completions",
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
            get_api_keys_for_url=lambda url: ["key-a"],
            choose_api_key_for_url=lambda url, exclude=None: {
                "key": "key-a",
                "from_pool": True,
                "pool_name": "pool",
                "key_index": 0,
                "key_count": 1,
                "key_id": "key-a",
            },
            mark_api_key_success=lambda url, key: None,
            mark_api_key_failure=lambda url, key, reason, force_cooldown=False: key_failures.append(
                (url, reason, force_cooldown)
            ),
            mark_route_success=lambda url: None,
            mark_route_failure=lambda url, reason: route_failures.append((url, reason)),
            response_indicates_model_unavailable=lambda response: False,
            classify_upstream_response=lambda response: ("return", f"status_{response.status_code}"),
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
                "https://timeout.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
        )
        self.assertEqual(attempts[0]["kind"], "exception")
        self.assertEqual(route_failures, [])
        self.assertEqual(key_failures, [])

    def test_route_switch_replaces_authorization_in_isolated_headers(self):
        sent_headers = []

        def sender(**kwargs):
            sent_headers.append((kwargs["url"], dict(kwargs.get("headers") or {})))
            if kwargs["url"] == "https://first.example/v1/chat/completions":
                return make_response(504, '{"error":{"message":"temporary"}}', kwargs["url"])
            return make_response(200, '{"ok":true}', kwargs["url"])

        key_by_url = {
            "https://first.example/v1/chat/completions": "first-key",
            "https://second.example/v1/chat/completions": "second-key",
        }

        response, attempts, error = request_upstream_with_retries(
            {
                "method": "POST",
                "url": "https://first.example/v1/chat/completions",
                "headers": {"Authorization": "Bearer stale-key", "Content-Type": "application/json"},
                "json": {"model": "demo"},
            },
            subpath="chat/completions",
            request_id="test-auth-isolation",
            upstream_urls=[
                "https://first.example/v1/chat/completions",
                "https://second.example/v1/chat/completions",
            ],
            model_candidates=["demo"],
            should_retry_request=lambda subpath, method: True,
            max_retries=3,
            should_enforce_route_switch_window=lambda urls, retry_allowed: True,
            route_switch_window_seconds=30,
            build_attempt_url_cycle=lambda urls, blocked: [url for url in urls if url not in blocked],
            build_model_candidate_order_for_route=lambda route, models, kwargs, request_id: {"candidates": models},
            should_race_model_candidates_for_route=lambda **kwargs: False,
            get_api_keys_for_url=lambda url: [key_by_url[url]],
            choose_api_key_for_url=lambda url, exclude=None: {
                "key": key_by_url[url],
                "from_pool": True,
                "pool_name": "pool",
                "key_index": 0,
                "key_count": 1,
                "key_id": key_by_url[url],
            },
            mark_api_key_success=lambda url, key: None,
            mark_api_key_failure=lambda url, key, reason, force_cooldown=False: None,
            mark_route_success=lambda url: None,
            mark_route_failure=lambda url, reason: None,
            response_indicates_model_unavailable=lambda response: False,
            classify_upstream_response=lambda response: (
                ("switch_route", f"route_switch_{response.status_code}")
                if response.status_code >= 500
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
        self.assertEqual(attempts[-1]["action"], "return")
        self.assertEqual(sent_headers[0][1]["Authorization"], "Bearer first-key")
        self.assertEqual(sent_headers[1][1]["Authorization"], "Bearer second-key")
        self.assertEqual(sent_headers[0][1]["Content-Type"], "application/json")
        self.assertEqual(sent_headers[1][1]["Content-Type"], "application/json")

    def test_deterministic_billing_error_marks_route_and_key_failure(self):
        key_failures = []
        route_failures = []

        def sender(**kwargs):
            return make_response(
                402,
                '{"error":{"message":"payment required: insufficient balance"}}',
                kwargs["url"],
            )

        response, attempts, error = request_upstream_with_retries(
            {"method": "POST", "url": "https://billing.example/v1/chat/completions", "json": {"model": "demo"}},
            subpath="chat/completions",
            request_id="test-billing",
            upstream_urls=["https://billing.example/v1/chat/completions"],
            model_candidates=["demo"],
            should_retry_request=lambda subpath, method: True,
            max_retries=3,
            should_enforce_route_switch_window=lambda urls, retry_allowed: True,
            route_switch_window_seconds=30,
            build_attempt_url_cycle=lambda urls, blocked: [url for url in urls if url not in blocked],
            build_model_candidate_order_for_route=lambda route, models, kwargs, request_id: {"candidates": models},
            should_race_model_candidates_for_route=lambda **kwargs: False,
            get_api_keys_for_url=lambda url: ["key-a"],
            choose_api_key_for_url=lambda url, exclude=None: {
                "key": "key-a",
                "from_pool": True,
                "pool_name": "pool",
                "key_index": 0,
                "key_count": 1,
                "key_id": "key-a",
            },
            mark_api_key_success=lambda url, key: None,
            mark_api_key_failure=lambda url, key, reason, force_cooldown=False: key_failures.append(
                (url, reason, force_cooldown)
            ),
            mark_route_success=lambda url: None,
            mark_route_failure=lambda url, reason: route_failures.append((url, reason)),
            response_indicates_model_unavailable=lambda response: False,
            classify_upstream_response=lambda response: ("switch_route", f"route_switch_{response.status_code}"),
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
        self.assertEqual(response.status_code, 402)
        self.assertEqual(attempts[0]["status_code"], 402)
        self.assertEqual(route_failures, [("https://billing.example/v1/chat/completions", "route_switch_402")])
        self.assertEqual(
            key_failures,
            [("https://billing.example/v1/chat/completions", "route_switch_402", True)],
        )

    def test_429_switches_to_next_route_instead_of_retrying_same_limited_route(self):
        sent_urls = []

        def sender(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if url == "https://limited.example/v1/chat/completions":
                return make_response(
                    429,
                    '{"status":429,"title":"Too Many Requests"}',
                    url,
                )
            return make_response(200, '{"ok":true}', url)

        response, attempts, error = request_upstream_with_retries(
            {"method": "POST", "url": "https://limited.example/v1/chat/completions", "json": {"model": "demo"}},
            subpath="chat/completions",
            request_id="test-429-switch",
            upstream_urls=[
                "https://limited.example/v1/chat/completions",
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
            get_api_keys_for_url=lambda url: ["key-a"],
            choose_api_key_for_url=lambda url, exclude=None: {
                "key": "key-a",
                "from_pool": True,
                "pool_name": "pool",
                "key_index": 0,
                "key_count": 1,
                "key_id": "key-a",
            },
            mark_api_key_success=lambda url, key: None,
            mark_api_key_failure=lambda url, key, reason, force_cooldown=False: None,
            mark_route_success=lambda url: None,
            mark_route_failure=lambda url, reason: None,
            response_indicates_model_unavailable=lambda response: False,
            classify_upstream_response=lambda response: (
                ("switch_route", f"route_switch_{response.status_code}")
                if response.status_code == 429
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
                "https://limited.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
        )
        self.assertEqual(attempts[0]["status_code"], 429)
        self.assertEqual(attempts[0]["action"], "switch_route")


if __name__ == "__main__":
    unittest.main()
