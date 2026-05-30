import unittest
from unittest.mock import patch

import requests

from local_proxy.server import (
    REQUEST_TIMEOUT,
    STREAM_FIRST_EVENT_TIMEOUT_SECONDS,
    STREAM_READ_TIMEOUT_SECONDS,
    prepare_route_switch_stream_request_kwargs,
    should_send_upstream_stream,
)
from local_proxy.upstream.orchestrator import request_upstream_with_retries
from local_proxy.upstream.router import build_attempt_url_cycle, build_route_selection_debug, mark_route_failure


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


class StreamingSuccessResponse:
    def __init__(self, url: str):
        self.status_code = 200
        self.url = url
        self.headers = {"Content-Type": "text/event-stream"}

    @property
    def content(self):
        raise AssertionError("stream body should not be consumed before proxy handoff")

    def close(self):
        return None


class GatewayFailoverTests(unittest.TestCase):
    def test_prepare_route_switch_stream_request_kwargs_uses_shorter_connect_timeout_for_multi_route_streams(self):
        request_kwargs = {
            "method": "POST",
            "url": "https://first.example/v1/chat/completions",
            "json": {"model": "demo", "stream": True},
            "stream": True,
            "timeout": (20, 600),
        }

        prepared = prepare_route_switch_stream_request_kwargs(
            request_kwargs,
            upstream_urls=[
                "https://first.example/v1/chat/completions",
                "https://second.example/v1/chat/completions",
            ],
        )

        self.assertNotEqual(prepared["timeout"], (20, 600))
        self.assertLessEqual(prepared["timeout"][0], prepared["timeout"][1])
        self.assertGreaterEqual(prepared["timeout"][1], prepared["timeout"][0])

    def test_prepare_route_switch_stream_request_kwargs_treats_same_base_route_ids_as_independent_routes(self):
        request_kwargs = {
            "method": "POST",
            "url": "https://integrate.api.nvidia.com/v1/chat/completions",
            "json": {"model": "demo", "stream": True},
            "stream": True,
            "timeout": (20, 600),
        }

        prepared = prepare_route_switch_stream_request_kwargs(
            request_kwargs,
            upstream_urls=[
                "https://integrate.api.nvidia.com/v1/chat/completions#__route=one",
                "https://integrate.api.nvidia.com/v1/chat/completions#__route=two",
                "https://integrate.api.nvidia.com/v1/chat/completions#__route=three",
            ],
        )

        self.assertEqual(
            prepared["timeout"],
            prepare_route_switch_stream_request_kwargs(
                request_kwargs,
                upstream_urls=[
                    "https://first.example/v1/chat/completions",
                    "https://second.example/v1/chat/completions",
                    "https://third.example/v1/chat/completions",
                ],
            )["timeout"],
        )

    def test_prepare_route_switch_stream_request_kwargs_uses_first_event_budget_even_when_lower_than_request_timeout(self):
        request_kwargs = {
            "method": "POST",
            "url": "https://integrate.api.nvidia.com/v1/chat/completions",
            "json": {"model": "demo", "stream": True},
            "stream": True,
            "timeout": (20, 600),
        }

        with patch("local_proxy.server.REQUEST_TIMEOUT", 180), patch(
            "local_proxy.server.STREAM_FIRST_EVENT_TIMEOUT_SECONDS",
            20,
        ), patch("local_proxy.server.STREAM_ROUTE_SWITCH_CONNECT_TIMEOUT_SECONDS", 5), patch(
            "local_proxy.server.UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS",
            60,
        ):
            prepared = prepare_route_switch_stream_request_kwargs(
                request_kwargs,
                upstream_urls=[
                    "https://integrate.api.nvidia.com/v1/chat/completions#__route=one",
                    "https://integrate.api.nvidia.com/v1/chat/completions#__route=two",
                    "https://integrate.api.nvidia.com/v1/chat/completions#__route=three",
                ],
            )

        self.assertEqual(prepared["timeout"], (5, 20))

    def test_prepare_route_switch_stream_request_kwargs_caps_preconnect_read_timeout_by_route_window(self):
        request_kwargs = {
            "method": "POST",
            "url": "https://integrate.api.nvidia.com/v1/chat/completions",
            "json": {"model": "demo", "stream": True},
            "stream": True,
            "timeout": (20, 600),
        }

        with patch("local_proxy.server.REQUEST_TIMEOUT", 180), patch(
            "local_proxy.server.STREAM_FIRST_EVENT_TIMEOUT_SECONDS",
            20,
        ), patch("local_proxy.server.STREAM_ROUTE_SWITCH_CONNECT_TIMEOUT_SECONDS", 5), patch(
            "local_proxy.server.UPSTREAM_ROUTE_SWITCH_WINDOW_SECONDS",
            5,
        ):
            prepared = prepare_route_switch_stream_request_kwargs(
                request_kwargs,
                upstream_urls=[
                    "https://integrate.api.nvidia.com/v1/chat/completions#__route=one",
                    "https://integrate.api.nvidia.com/v1/chat/completions#__route=two",
                    "https://integrate.api.nvidia.com/v1/chat/completions#__route=three",
                ],
            )

        self.assertEqual(prepared["timeout"], (5, 5))

    def test_prepare_route_switch_stream_request_kwargs_does_not_shorten_timeout_for_non_stream_requests(self):
        request_kwargs = {
            "method": "POST",
            "url": "https://first.example/v1/chat/completions",
            "json": {"model": "demo", "stream": True},
            "stream": False,
            "timeout": 30,
        }

        prepared = prepare_route_switch_stream_request_kwargs(
            request_kwargs,
            upstream_urls=[
                "https://first.example/v1/chat/completions",
                "https://second.example/v1/chat/completions",
            ],
        )

        self.assertEqual(prepared["timeout"], 30)

    def test_should_send_upstream_stream_respects_forced_upstream_stream(self):
        self.assertFalse(should_send_upstream_stream(requested_stream=False, upstream_stream=False))
        self.assertTrue(should_send_upstream_stream(requested_stream=False, upstream_stream=True))
        self.assertTrue(should_send_upstream_stream(requested_stream=True, upstream_stream=False))

    def test_internal_meta_is_not_forwarded_to_request_sender(self):
        captured_kwargs = {}

        def sender(**kwargs):
            captured_kwargs.update(kwargs)
            return make_response(200, '{"ok":true}', kwargs["url"])

        response, attempts, error = request_upstream_with_retries(
            {
                "method": "POST",
                "url": "https://ok.example/v1/chat/completions",
                "json": {"model": "demo"},
                "headers": {"Content-Type": "application/json"},
                "meta": {"session_affinity_key": "session-1"},
            },
            subpath="chat/completions",
            request_id="test-meta-strip",
            upstream_urls=["https://ok.example/v1/chat/completions"],
            model_candidates=["demo"],
            should_retry_request=lambda subpath, method: True,
            max_retries=1,
            should_enforce_route_switch_window=lambda urls, retry_allowed: False,
            route_switch_window_seconds=30,
            build_attempt_url_cycle=lambda urls, blocked: [url for url in urls if url not in blocked],
            build_model_candidate_order_for_route=lambda route, models, kwargs, request_id: {"candidates": models},
            should_race_model_candidates_for_route=lambda **kwargs: False,
            get_api_keys_for_url=lambda url: [],
            choose_api_key_for_url=lambda url, exclude=None: {},
            mark_api_key_success=lambda url, key: None,
            mark_api_key_failure=lambda url, key, reason, force_cooldown=False: None,
            mark_route_success=lambda url: None,
            mark_route_failure=lambda url, reason: None,
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
        self.assertNotIn("meta", captured_kwargs)
        self.assertEqual(len(attempts), 1)

    def test_route_cycle_prefers_session_affinity_route(self):
        route_health = {}
        route_selection_state = {
            "affinity:session-1": {
                "route_url": "https://b.example/v1/chat/completions",
                "last_used_at": 1.0,
            }
        }

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        ordered = build_attempt_url_cycle(
            [
                "https://a.example/v1/chat/completions",
                "https://b.example/v1/chat/completions",
                "https://c.example/v1/chat/completions",
            ],
            set(),
            route_health=route_health,
            route_selection_state=route_selection_state,
            state_lock=DummyLock(),
            randomize_endpoints=False,
            route_score_provider=lambda url: 0.0,
            session_affinity_key="session-1",
        )

        self.assertEqual(ordered[0], "https://b.example/v1/chat/completions")

    def test_route_cycle_ignores_fingerprint_affinity_when_randomization_enabled(self):
        route_health = {}
        route_selection_state = {
            "affinity:session:v1:fingerprint:test": {
                "route_url": "https://b.example/v1/chat/completions",
                "last_used_at": 1.0,
            }
        }

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("builtins.hash", return_value=0), patch("local_proxy.upstream.router.random.shuffle", lambda seq: None):
            ordered = build_attempt_url_cycle(
                [
                    "https://a.example/v1/chat/completions",
                    "https://b.example/v1/chat/completions",
                    "https://c.example/v1/chat/completions",
                ],
                set(),
                route_health=route_health,
                route_selection_state=route_selection_state,
                state_lock=DummyLock(),
                randomize_endpoints=True,
                route_score_provider=lambda url: 10.0 if url.endswith("c.example/v1/chat/completions") else 0.0,
                session_affinity_key="session:v1:fingerprint:test",
            )

        self.assertEqual(ordered[0], "https://c.example/v1/chat/completions")

    def test_route_cycle_keeps_explicit_affinity_even_when_randomization_enabled(self):
        route_health = {}
        route_selection_state = {
            "affinity:session:v1:explicit:test": {
                "route_url": "https://b.example/v1/chat/completions",
                "last_used_at": 1.0,
            }
        }

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("builtins.hash", return_value=0), patch("local_proxy.upstream.router.random.shuffle", lambda seq: None):
            ordered = build_attempt_url_cycle(
                [
                    "https://a.example/v1/chat/completions",
                    "https://b.example/v1/chat/completions",
                    "https://c.example/v1/chat/completions",
                ],
                set(),
                route_health=route_health,
                route_selection_state=route_selection_state,
                state_lock=DummyLock(),
                randomize_endpoints=True,
                route_score_provider=lambda url: 10.0 if url.endswith("c.example/v1/chat/completions") else 0.0,
                session_affinity_key="session:v1:explicit:test",
            )

        self.assertEqual(ordered[0], "https://b.example/v1/chat/completions")

    def test_route_cycle_keeps_highest_priority_route_first_across_repeated_calls(self):
        route_health = {}
        route_selection_state = {}

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        route_scores = {
            "https://a.example/v1/chat/completions": 103.0,
            "https://b.example/v1/chat/completions": 102.0,
            "https://c.example/v1/chat/completions": 101.0,
        }

        with patch("local_proxy.upstream.router.time.time", return_value=1000.0):
            ordered_first = build_attempt_url_cycle(
                list(route_scores.keys()),
                set(),
                route_health=route_health,
                route_selection_state=route_selection_state,
                state_lock=DummyLock(),
                randomize_endpoints=False,
                route_score_provider=lambda url: route_scores[url],
                session_affinity_key="",
            )
            ordered_second = build_attempt_url_cycle(
                list(route_scores.keys()),
                set(),
                route_health=route_health,
                route_selection_state=route_selection_state,
                state_lock=DummyLock(),
                randomize_endpoints=False,
                route_score_provider=lambda url: route_scores[url],
                session_affinity_key="",
            )

        self.assertEqual(ordered_first[0], "https://a.example/v1/chat/completions")
        self.assertEqual(ordered_second[0], "https://a.example/v1/chat/completions")

    def test_route_cycle_randomization_does_not_demote_higher_priority_route(self):
        route_health = {}
        route_selection_state = {}

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        route_scores = {
            "https://a.example/v1/chat/completions": 103.0,
            "https://b.example/v1/chat/completions": 102.0,
            "https://c.example/v1/chat/completions": 101.0,
        }

        with patch("local_proxy.upstream.router.time.time", return_value=1000.0), patch("builtins.hash", return_value=2):
            ordered = build_attempt_url_cycle(
                list(route_scores.keys()),
                set(),
                route_health=route_health,
                route_selection_state=route_selection_state,
                state_lock=DummyLock(),
                randomize_endpoints=True,
                route_score_provider=lambda url: route_scores[url],
                session_affinity_key="",
            )

        self.assertEqual(ordered[0], "https://a.example/v1/chat/completions")

    def test_route_selection_debug_marks_randomized_fingerprint_as_ignored(self):
        route_health = {}

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        debug_meta = build_route_selection_debug(
            [
                "https://a.example/v1/chat/completions",
                "https://b.example/v1/chat/completions",
            ],
            set(),
            route_health=route_health,
            state_lock=DummyLock(),
            randomize_endpoints=True,
            session_affinity_key="session:v1:fingerprint:test",
        )

        self.assertEqual(debug_meta["session_affinity_type"], "fingerprint")
        self.assertFalse(debug_meta["session_affinity_applied"])
        self.assertEqual(debug_meta["rotation_reason"], "randomized_ignore_fingerprint_affinity")

    def test_streaming_success_response_is_returned_without_preconsuming_body(self):
        stream_response = StreamingSuccessResponse("https://slow.example/v1/chat/completions")

        response, attempts, error = request_upstream_with_retries(
            {
                "method": "POST",
                "url": "https://slow.example/v1/chat/completions",
                "json": {"model": "demo", "stream": True},
                "headers": {"Content-Type": "application/json"},
                "stream": True,
                "timeout": (5, 5),
            },
            subpath="chat/completions",
            request_id="test-stream-success-deferred",
            upstream_urls=["https://slow.example/v1/chat/completions"],
            model_candidates=["demo"],
            should_retry_request=lambda subpath, method: True,
            max_retries=1,
            should_enforce_route_switch_window=lambda urls, retry_allowed: True,
            route_switch_window_seconds=5,
            build_attempt_url_cycle=lambda urls, blocked: [url for url in urls if url not in blocked],
            build_model_candidate_order_for_route=lambda route, models, kwargs, request_id: {"candidates": models},
            should_race_model_candidates_for_route=lambda **kwargs: False,
            get_api_keys_for_url=lambda url: [],
            choose_api_key_for_url=lambda url, exclude=None: {},
            mark_api_key_success=lambda url, key: None,
            mark_api_key_failure=lambda url, key, reason, force_cooldown=False: None,
            mark_route_success=lambda url: None,
            mark_route_failure=lambda url, reason: None,
            response_indicates_model_unavailable=lambda response: (_ for _ in ()).throw(
                AssertionError("stream success should not be classified before handoff")
            ),
            classify_upstream_response=lambda response: (_ for _ in ()).throw(
                AssertionError("stream success should not be classified before handoff")
            ),
            extract_error_preview_from_response=lambda response: (_ for _ in ()).throw(
                AssertionError("stream success preview should not be read before handoff")
            ),
            apply_model_candidate_to_request_kwargs=lambda kwargs, model: dict(kwargs),
            apply_learned_completion_limit_to_request_kwargs=lambda *args, **kwargs: 0,
            extract_completion_token_limit_from_response=lambda response: None,
            extract_context_token_limit_from_response=lambda response: (None, None),
            clamp_payload_output_tokens=lambda payload, limit: 0,
            record_learned_model_capability=lambda **kwargs: None,
            record_model_candidate_result=lambda **kwargs: None,
            compute_retry_delay_ms=lambda attempt, response=None: 0,
            remaining_retry_window_ms=lambda deadline: 5000,
            append_race_attempts=lambda attempts, race_attempts, **kwargs: set(),
            model_candidate_differs_from_logical=lambda logical, candidate: False,
            logger=NullLogger(),
            cache_stat_bump=lambda key: None,
            model_candidate_race_limit=1,
            model_candidate_race_timeout_seconds=1,
            enable_model_candidate_race=False,
            request_sender=lambda **kwargs: stream_response,
        )

        self.assertIsNone(error)
        self.assertIs(response, stream_response)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["status_code"], 200)
        self.assertEqual(attempts[0]["action"], "return")
        self.assertEqual(attempts[0]["reason"], "stream_success_deferred_200")

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
        self.assertEqual(route_failures, [("https://bad.example/v1/chat/completions", "route_switch_504")])
        self.assertEqual(key_failures, [])

    def test_404_page_not_found_switches_to_next_healthy_route(self):
        sent_urls = []
        route_failures = []

        def sender(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if url == "https://bad.example/v1/chat/completions":
                return make_response(404, "404 page not found", url)
            return make_response(200, '{"ok":true}', url)

        response, attempts, error = request_upstream_with_retries(
            {"method": "POST", "url": "https://bad.example/v1/chat/completions", "json": {"model": "demo"}},
            subpath="chat/completions",
            request_id="test-404-route-switch",
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
            mark_route_failure=lambda url, reason: route_failures.append((url, reason)),
            response_indicates_model_unavailable=lambda response: False,
            classify_upstream_response=lambda response: (
                ("switch_route", "route_not_found_404")
                if response.status_code == 404 and "page not found" in response.text.lower()
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
        self.assertEqual(attempts[0]["status_code"], 404)
        self.assertEqual(attempts[0]["action"], "switch_route")
        self.assertEqual(route_failures, [("https://bad.example/v1/chat/completions", "route_not_found_404")])

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
        self.assertEqual(route_failures, [("https://timeout.example/v1/chat/completions", "request_exception")])
        self.assertEqual(key_failures, [])

    def test_request_exception_allows_only_one_immediate_followup_after_window_expires(self):
        sent_urls = []

        def sender(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if "good.example" in url:
                return make_response(200, '{"ok":true}', url)
            raise requests.Timeout("read timed out")

        response, attempts, error = request_upstream_with_retries(
            {"method": "POST", "url": "https://bad-a.example/v1/chat/completions", "json": {"model": "demo"}, "timeout": (3, 6)},
            subpath="chat/completions",
            request_id="test-timeout-budget",
            upstream_urls=[
                "https://bad-a.example/v1/chat/completions",
                "https://bad-b.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
            model_candidates=["demo"],
            should_retry_request=lambda subpath, method: True,
            max_retries=3,
            should_enforce_route_switch_window=lambda urls, retry_allowed: True,
            route_switch_window_seconds=1,
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
            remaining_retry_window_ms=lambda deadline: 0,
            append_race_attempts=lambda attempts, race_attempts, **kwargs: set(),
            model_candidate_differs_from_logical=lambda logical, candidate: False,
            logger=NullLogger(),
            cache_stat_bump=lambda key: None,
            model_candidate_race_limit=1,
            model_candidate_race_timeout_seconds=1,
            enable_model_candidate_race=False,
            request_sender=sender,
        )

        self.assertIsInstance(error, requests.Timeout)
        self.assertIsNone(response)
        self.assertEqual(
            sent_urls,
            [
                "https://bad-a.example/v1/chat/completions",
                "https://bad-b.example/v1/chat/completions",
            ],
        )
        self.assertEqual(len(attempts), 2)

    def test_request_exception_clamps_followup_stream_timeout_to_remaining_window(self):
        seen_timeouts = []

        remaining_values = iter([5000, 0, 0])

        def remaining_window(_deadline):
            return next(remaining_values, 0)

        def sender(**kwargs):
            seen_timeouts.append(kwargs.get("timeout"))
            raise requests.Timeout("read timed out")

        response, attempts, error = request_upstream_with_retries(
            {
                "method": "POST",
                "url": "https://bad-a.example/v1/chat/completions",
                "json": {"model": "demo", "stream": True},
                "stream": True,
                "timeout": (3, 6),
            },
            subpath="chat/completions",
            request_id="test-timeout-clamp",
            upstream_urls=[
                "https://bad-a.example/v1/chat/completions",
                "https://bad-b.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
            model_candidates=["demo"],
            should_retry_request=lambda subpath, method: True,
            max_retries=3,
            should_enforce_route_switch_window=lambda urls, retry_allowed: True,
            route_switch_window_seconds=5,
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
            remaining_retry_window_ms=remaining_window,
            append_race_attempts=lambda attempts, race_attempts, **kwargs: set(),
            model_candidate_differs_from_logical=lambda logical, candidate: False,
            logger=NullLogger(),
            cache_stat_bump=lambda key: None,
            model_candidate_race_limit=1,
            model_candidate_race_timeout_seconds=1,
            enable_model_candidate_race=False,
            request_sender=sender,
        )

        self.assertIsNone(response)
        self.assertIsInstance(error, requests.Timeout)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(seen_timeouts, [(3, 5), (1, 1)])

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

    def test_route_switch_clears_authorization_for_keyless_route(self):
        sent_headers = []

        def sender(**kwargs):
            sent_headers.append((kwargs["url"], dict(kwargs.get("headers") or {})))
            if kwargs["url"] == "https://keyed.example/v1/chat/completions":
                return make_response(504, '{"error":{"message":"temporary"}}', kwargs["url"])
            return make_response(200, '{"ok":true}', kwargs["url"])

        def choose_key(url, exclude=None):
            if url == "https://keyed.example/v1/chat/completions":
                return {
                    "key": "first-key",
                    "from_pool": True,
                    "pool_name": "keyed",
                    "key_index": 0,
                    "key_count": 1,
                    "key_id": "first-key",
                }
            return {}

        response, attempts, error = request_upstream_with_retries(
            {
                "method": "POST",
                "url": "https://keyed.example/v1/chat/completions",
                "headers": {"Authorization": "Bearer stale-key", "Content-Type": "application/json"},
                "json": {"model": "demo"},
            },
            subpath="chat/completions",
            request_id="test-keyless-auth-clear",
            upstream_urls=[
                "https://keyed.example/v1/chat/completions",
                "https://free.example/v1/chat/completions",
            ],
            model_candidates=["demo"],
            should_retry_request=lambda subpath, method: True,
            max_retries=3,
            should_enforce_route_switch_window=lambda urls, retry_allowed: True,
            route_switch_window_seconds=30,
            build_attempt_url_cycle=lambda urls, blocked: [url for url in urls if url not in blocked],
            build_model_candidate_order_for_route=lambda route, models, kwargs, request_id: {"candidates": models},
            should_race_model_candidates_for_route=lambda **kwargs: False,
            get_api_keys_for_url=lambda url: ["first-key"] if "keyed.example" in url else [],
            choose_api_key_for_url=choose_key,
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
        self.assertEqual(sent_headers[0][1]["Authorization"], "Bearer first-key")
        self.assertNotIn("Authorization", sent_headers[1][1])
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
        route_failures = []

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
            mark_route_failure=lambda url, reason: route_failures.append((url, reason)),
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
        self.assertEqual(route_failures, [("https://limited.example/v1/chat/completions", "route_switch_429")])

    def test_429_can_retry_same_route_with_configured_exponential_backoff_before_switching(self):
        sent_urls = []
        route_failures = []
        sleeps = []
        limited_route = "https://limited.example/v1/chat/completions"
        good_route = "https://good.example/v1/chat/completions"

        def sender(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if url == limited_route and sent_urls.count(limited_route) <= 3:
                return make_response(429, '{"status":429,"title":"Too Many Requests"}', url)
            return make_response(200, '{"ok":true}', url)

        with patch("local_proxy.upstream.orchestrator.time.sleep", side_effect=lambda seconds: sleeps.append(seconds)):
            response, attempts, error = request_upstream_with_retries(
                {"method": "POST", "url": limited_route, "json": {"model": "demo"}},
                subpath="chat/completions",
                request_id="test-429-rate-limit-backoff",
                upstream_urls=[limited_route, good_route],
                model_candidates=["demo"],
                should_retry_request=lambda subpath, method: True,
                max_retries=4,
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
                mark_route_failure=lambda url, reason: route_failures.append((url, reason)),
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
                get_rate_limit_retry_attempts=lambda url: 2 if url == limited_route else 0,
                compute_rate_limit_retry_delay_ms=lambda url, retry_index, response=None: 1000 * (2 ** (retry_index - 1)),
            )

        self.assertIsNone(error)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sent_urls, [limited_route, limited_route, limited_route, good_route])
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertEqual(attempts[0]["action"], "retry_rate_limit")
        self.assertEqual(attempts[0]["rate_limit_retry_delay_ms"], 1000)
        self.assertEqual(attempts[1]["action"], "retry_rate_limit")
        self.assertEqual(attempts[1]["rate_limit_retry_delay_ms"], 2000)
        self.assertEqual(attempts[2]["action"], "switch_route")
        self.assertEqual(route_failures, [(limited_route, "route_switch_429")] * 3)

    def test_non_requests_exception_switches_to_next_route_and_preserves_attempt_route(self):
        sent_urls = []
        route_failures = []

        def sender(**kwargs):
            url = kwargs["url"]
            sent_urls.append(url)
            if url == "https://broken.example/v1/chat/completions":
                raise RuntimeError("unexpected sender boom")
            return make_response(200, '{"ok":true}', url)

        response, attempts, error = request_upstream_with_retries(
            {"method": "POST", "url": "https://broken.example/v1/chat/completions", "json": {"model": "demo"}},
            subpath="chat/completions",
            request_id="test-non-requests-exception-switch",
            upstream_urls=[
                "https://broken.example/v1/chat/completions",
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
                "https://broken.example/v1/chat/completions",
                "https://good.example/v1/chat/completions",
            ],
        )
        self.assertEqual(attempts[0]["route_url"], "https://broken.example/v1/chat/completions")
        self.assertEqual(attempts[0]["kind"], "exception")
        self.assertEqual(attempts[0]["error"], "unexpected sender boom")
        self.assertEqual(route_failures, [("https://broken.example/v1/chat/completions", "request_exception")])

    def test_429_switches_between_distinct_routes_even_when_request_url_is_same(self):
        sent_urls = []
        route_failures = []
        route_a = "https://integrate.api.nvidia.com/v1/chat/completions#__route=nv1"
        route_b = "https://integrate.api.nvidia.com/v1/chat/completions#__route=nv2"

        def sender(**kwargs):
            sent_urls.append(kwargs["url"])
            if len(sent_urls) == 1:
                return make_response(429, '{"status":429,"title":"Too Many Requests"}', kwargs["url"])
            return make_response(200, '{"ok":true}', kwargs["url"])

        response, attempts, error = request_upstream_with_retries(
            {"method": "POST", "url": "https://integrate.api.nvidia.com/v1/chat/completions", "json": {"model": "demo"}},
            subpath="chat/completions",
            request_id="test-same-url-route-switch",
            upstream_urls=[route_a, route_b],
            model_candidates=["demo"],
            should_retry_request=lambda subpath, method: True,
            max_retries=3,
            should_enforce_route_switch_window=lambda urls, retry_allowed: True,
            route_switch_window_seconds=30,
            build_attempt_url_cycle=lambda urls, blocked: [url for url in urls if url not in blocked],
            build_model_candidate_order_for_route=lambda route, models, kwargs, request_id: {"candidates": models},
            should_race_model_candidates_for_route=lambda **kwargs: False,
            get_api_keys_for_url=lambda url: ["key-a"] if url == route_a else ["key-b"],
            choose_api_key_for_url=lambda url, exclude=None: {
                "key": "key-a" if url == route_a else "key-b",
                "from_pool": True,
                "pool_name": "nv1" if url == route_a else "nv2",
                "key_index": 0,
                "key_count": 1,
                "key_id": "key-a" if url == route_a else "key-b",
            },
            mark_api_key_success=lambda url, key: None,
            mark_api_key_failure=lambda url, key, reason, force_cooldown=False: None,
            mark_route_success=lambda url: None,
            mark_route_failure=lambda url, reason: route_failures.append((url, reason)),
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
                "https://integrate.api.nvidia.com/v1/chat/completions",
                "https://integrate.api.nvidia.com/v1/chat/completions",
            ],
        )
        self.assertEqual(attempts[0]["route_url"], route_a)
        self.assertEqual(attempts[1]["route_url"], route_b)
        self.assertEqual(route_failures, [(route_a, "route_switch_429")])

    def test_route_failure_cooldown_supports_policy_multiplier_and_cap(self):
        route_health = {}

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        state_lock = DummyLock()
        route_url = "https://limited.example/v1/chat/completions"

        mark_route_failure(
            route_health,
            state_lock,
            route_url,
            "route_switch_429",
            route_cooldown_seconds=10,
            route_switch_window_seconds=1,
            route_failure_threshold=1,
            route_cooldown_multiplier=2.0,
            route_cooldown_max_seconds=25,
        )
        first_until = route_health[route_url]["cooldown_until"]
        first_failure_at = route_health[route_url]["last_failure_at"]
        self.assertAlmostEqual(first_until - first_failure_at, 10, delta=2)

        mark_route_failure(
            route_health,
            state_lock,
            route_url,
            "route_switch_429",
            route_cooldown_seconds=10,
            route_switch_window_seconds=1,
            route_failure_threshold=1,
            route_cooldown_multiplier=2.0,
            route_cooldown_max_seconds=25,
        )
        second_until = route_health[route_url]["cooldown_until"]
        second_failure_at = route_health[route_url]["last_failure_at"]
        self.assertAlmostEqual(second_until - second_failure_at, 20, delta=2)

        mark_route_failure(
            route_health,
            state_lock,
            route_url,
            "route_switch_429",
            route_cooldown_seconds=10,
            route_switch_window_seconds=1,
            route_failure_threshold=1,
            route_cooldown_multiplier=2.0,
            route_cooldown_max_seconds=25,
        )
        third_until = route_health[route_url]["cooldown_until"]
        third_failure_at = route_health[route_url]["last_failure_at"]
        self.assertAlmostEqual(third_until - third_failure_at, 25, delta=2)

    def test_request_exception_cools_route_on_first_failure(self):
        route_health = {}

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        state_lock = DummyLock()
        route_url = "https://timeout.example/v1/chat/completions"

        mark_route_failure(
            route_health,
            state_lock,
            route_url,
            "request_exception",
            route_cooldown_seconds=10,
            route_switch_window_seconds=1,
            route_failure_threshold=3,
            route_cooldown_multiplier=2.0,
            route_cooldown_max_seconds=25,
        )

        entry = route_health[route_url]
        self.assertEqual(entry["consecutive_failures"], 1)
        self.assertGreater(entry["cooldown_until"], entry["last_failure_at"])

    def test_route_not_found_cools_route_on_first_failure(self):
        route_health = {}

        class DummyLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        state_lock = DummyLock()
        route_url = "https://bad.example/v1/chat/completions"

        mark_route_failure(
            route_health,
            state_lock,
            route_url,
            "route_not_found_404",
            route_cooldown_seconds=10,
            route_switch_window_seconds=1,
            route_failure_threshold=3,
            route_cooldown_multiplier=2.0,
            route_cooldown_max_seconds=25,
        )

        entry = route_health[route_url]
        self.assertEqual(entry["consecutive_failures"], 1)
        self.assertGreater(entry["cooldown_until"], entry["last_failure_at"])

if __name__ == "__main__":
    unittest.main()
