import importlib
import os
import tempfile
import unittest
from pathlib import Path

from local_proxy.http.proxy_auth import (
    build_proxy_api_key_failure_diagnostics,
    generate_proxy_api_key,
    hash_proxy_api_key,
    parse_proxy_api_keys,
    preview_proxy_api_key,
    verify_proxy_api_key,
)


class FakeRuntimeConfigStorage:
    def __init__(self):
        self.saved_payload = None
        self.saved_key = None
        self.loaded_payload = {}

    def save_app_config(self, payload, config_key="runtime_config"):
        self.saved_payload = payload
        self.saved_key = config_key

    def load_app_config(self, config_key="runtime_config"):
        self.saved_key = config_key
        return self.loaded_payload

    def save_pool_runtime_state(self, payload, state_key="default"):
        return None

    def clear_request_cache(self):
        self.request_cache_cleared = True


class ProxyApiAuthParserTests(unittest.TestCase):
    def test_generate_proxy_api_key_uses_openai_style_shape(self):
        generated_key = generate_proxy_api_key()

        self.assertRegex(generated_key, r"^sk-[A-Za-z0-9]{48}$")

    def test_parse_proxy_api_keys_supports_common_separators_and_dedupes(self):
        self.assertEqual(
            parse_proxy_api_keys(" key-a;key-b, key-a\nkey-c "),
            ("key-a", "key-b", "key-c"),
        )

    def test_verify_proxy_api_key_accepts_bearer_header(self):
        from flask import Flask, request

        app = Flask(__name__)
        with app.test_request_context(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-secret"},
        ):
            result = verify_proxy_api_key(request, ("proxy-secret",))

        self.assertTrue(result.ok)
        self.assertEqual(result.source, "authorization")

    def test_verify_proxy_api_key_accepts_x_api_key_header(self):
        from flask import Flask, request

        app = Flask(__name__)
        with app.test_request_context(
            "/v1/chat/completions",
            headers={"X-API-Key": "proxy-secret"},
        ):
            result = verify_proxy_api_key(request, ("proxy-secret",))

        self.assertTrue(result.ok)
        self.assertEqual(result.source, "x-api-key")

    def test_verify_proxy_api_key_prefers_dedicated_header_over_authorization(self):
        from flask import Flask, request

        app = Flask(__name__)
        with app.test_request_context(
            "/v1/messages",
            headers={
                "Authorization": "Bearer upstream-secret",
                "X-API-Key": "proxy-secret",
            },
        ):
            result = verify_proxy_api_key(request, ("proxy-secret",))

        self.assertTrue(result.ok)
        self.assertEqual(result.source, "x-api-key")

    def test_verify_proxy_api_key_accepts_proxy_authorization_bearer(self):
        from flask import Flask, request

        app = Flask(__name__)
        with app.test_request_context(
            "/v1/messages",
            headers={"Proxy-Authorization": "Bearer proxy-secret"},
        ):
            result = verify_proxy_api_key(request, ("proxy-secret",))

        self.assertTrue(result.ok)
        self.assertEqual(result.source, "proxy-authorization")

    def test_verify_proxy_api_key_accepts_query_key(self):
        from flask import Flask, request

        app = Flask(__name__)
        with app.test_request_context("/v1beta/models/demo:generateContent?key=proxy-secret"):
            result = verify_proxy_api_key(request, ("proxy-secret",))

        self.assertTrue(result.ok)
        self.assertEqual(result.source, "key")

    def test_build_proxy_api_key_failure_diagnostics_masks_candidate_and_lists_managed_previews(self):
        from flask import Flask, request

        app = Flask(__name__)
        managed_key = "sk-R3FgLkpc3lVrpotlu9tV9rNvvQLRsupzsozwG7pHo11vcbqr"
        with app.test_request_context(
            "/v1/messages",
            headers={"X-API-Key": "wrong-secret"},
        ):
            diagnostics = build_proxy_api_key_failure_diagnostics(
                request,
                (),
                [
                    {
                        "id": "pak_demo",
                        "key_hash": hash_proxy_api_key(managed_key),
                        "key_preview": preview_proxy_api_key(managed_key),
                        "enabled": True,
                        "name": "NEWAPI",
                    }
                ],
            )

        self.assertTrue(diagnostics["candidate_present"])
        self.assertEqual(diagnostics["source"], "x-api-key")
        self.assertNotEqual(diagnostics["candidate_preview"], "wrong-secret")
        self.assertEqual(diagnostics["managed_key_ids"], ["pak_demo"])
        self.assertEqual(len(diagnostics["managed_key_previews"]), 1)
        self.assertTrue(diagnostics["managed_key_previews"][0].startswith("sk-"))

    def test_build_session_affinity_key_uses_proxy_headers_for_explicit_affinity(self):
        from flask import Flask
        from local_proxy.server import build_session_affinity_key

        app = Flask(__name__)
        with app.test_request_context(
            "/v1/chat/completions",
            headers={"X-Proxy-Session-Key": "session-explicit"},
            json={"model": "demo", "messages": [{"role": "user", "content": "hello"}]},
        ):
            key = build_session_affinity_key(
                "openai_chat_completions",
                {"model": "demo", "messages": [{"role": "user", "content": "hello"}]},
            )

        self.assertTrue(key.startswith("session:v1:explicit:"))

    def test_build_session_affinity_key_treats_generic_session_headers_as_fingerprint_only(self):
        from flask import Flask
        from local_proxy.server import build_session_affinity_key

        app = Flask(__name__)
        with app.test_request_context(
            "/v1/chat/completions",
            headers={"X-Session-Id": "generic-session"},
            json={"model": "demo", "messages": [{"role": "user", "content": "hello"}]},
        ):
            key = build_session_affinity_key(
                "openai_chat_completions",
                {"model": "demo", "messages": [{"role": "user", "content": "hello"}]},
            )

        self.assertTrue(key.startswith("session:v1:fingerprint:"))


class ProxyEntrypointAuthTests(unittest.TestCase):
    def load_server_with_keys(self, value: str):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        env_overrides = {
            "PROXY_API_KEYS": value,
            "PROXY_CONFIG_PATH": str(Path(temp_dir.name) / "proxy-config.json"),
            "PROXY_REMOTE_CONFIG_PATH": str(Path(temp_dir.name) / "proxy-config.remote.json"),
            "STORAGE_DB_HOST": "",
            "STORAGE_DB_PORT": "3306",
            "STORAGE_DB_USER": "",
            "STORAGE_DB_PASSWORD": "",
            "STORAGE_DB_NAME": "",
        }
        previous = {key: os.environ.get(key) for key in env_overrides}
        for key, env_value in env_overrides.items():
            os.environ[key] = env_value

        import local_proxy.server as server

        server = importlib.reload(server)
        def restore_env():
            for key, old_value in previous.items():
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value

        self.addCleanup(restore_env)
        return server

    def test_models_root_requires_proxy_api_key_configuration(self):
        server = self.load_server_with_keys("")
        client = server.app.test_client()

        response = client.get("/v1", headers={"Accept": "application/json"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"]["code"], "proxy_api_key_not_configured")

    def test_models_root_rejects_missing_proxy_api_key(self):
        server = self.load_server_with_keys("proxy-secret")
        client = server.app.test_client()

        response = client.get("/v1", headers={"Accept": "application/json"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "proxy_api_key_missing")

    def test_chat_completions_rejects_missing_proxy_api_key_before_upstream(self):
        server = self.load_server_with_keys("proxy-secret")
        client = server.app.test_client()

        response = client.post(
            "/v1/chat/completions",
            json={"model": "demo", "messages": [{"role": "user", "content": "hi"}]},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "proxy_api_key_missing")

    def test_gemini_root_rejects_missing_proxy_api_key(self):
        server = self.load_server_with_keys("proxy-secret")
        client = server.app.test_client()

        response = client.get("/v1beta")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "proxy_api_key_missing")

    def test_models_root_rejects_invalid_proxy_api_key(self):
        server = self.load_server_with_keys("proxy-secret")
        client = server.app.test_client()

        response = client.get(
            "/v1",
            headers={"Accept": "application/json", "Authorization": "Bearer wrong-secret"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "proxy_api_key_invalid")

    def test_models_root_accepts_valid_proxy_api_key(self):
        server = self.load_server_with_keys("proxy-secret")
        client = server.app.test_client()

        response = client.get(
            "/v1",
            headers={"Accept": "application/json", "Authorization": "Bearer proxy-secret"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_debug_request_cache_clear_endpoint_works_for_authenticated_session(self):
        server = self.load_server_with_keys("")
        fake_storage = FakeRuntimeConfigStorage()
        fake_storage.request_cache_cleared = False
        server.storage = fake_storage
        client = server.app.test_client()
        with client.session_transaction() as session:
            session["_proxy_authed"] = True

        response = client.post("/debug/request-cache/clear")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertTrue(fake_storage.request_cache_cleared)

    def test_managed_proxy_key_can_be_created_used_disabled_and_deleted(self):
        server = self.load_server_with_keys("")
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        server.PROXY_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.json"
        server.PROXY_API_KEY_RECORDS = []
        client = server.app.test_client()
        with client.session_transaction() as session:
            session["_proxy_authed"] = True

        create_response = client.post(
            "/debug/proxy-keys",
            json={"action": "create", "name": "NEWAPI main"},
        )

        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.get_json()
        generated_key = create_payload["generated_key"]
        key_id = create_payload["keys"][0]["id"]
        self.assertRegex(generated_key, r"^sk-[A-Za-z0-9]{48}$")
        self.assertNotIn(generated_key, str(create_payload["keys"]))

        ok_response = client.get(
            "/v1",
            headers={"Accept": "application/json", "Authorization": f"Bearer {generated_key}"},
        )
        self.assertEqual(ok_response.status_code, 200)

        disable_response = client.post(
            "/debug/proxy-keys",
            json={"action": "update", "id": key_id, "enabled": False},
        )
        self.assertEqual(disable_response.status_code, 200)
        rejected_response = client.get(
            "/v1",
            headers={"Accept": "application/json", "Authorization": f"Bearer {generated_key}"},
        )
        self.assertEqual(rejected_response.status_code, 503)
        self.assertEqual(rejected_response.get_json()["error"]["code"], "proxy_api_key_not_configured")

        enable_response = client.post(
            "/debug/proxy-keys",
            json={"action": "update", "id": key_id, "enabled": True},
        )
        self.assertEqual(enable_response.status_code, 200)
        restored_response = client.get(
            "/v1",
            headers={"Accept": "application/json", "Authorization": f"Bearer {generated_key}"},
        )
        self.assertEqual(restored_response.status_code, 200)

        delete_response = client.post(
            "/debug/proxy-keys",
            json={"action": "delete", "id": key_id},
        )
        self.assertEqual(delete_response.status_code, 200)
        final_response = client.get(
            "/v1",
            headers={"Accept": "application/json", "Authorization": f"Bearer {generated_key}"},
        )
        self.assertEqual(final_response.status_code, 503)

    def test_managed_proxy_key_records_are_written_to_mysql_app_config_payload(self):
        server = self.load_server_with_keys("")
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        server.PROXY_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.json"
        fake_storage = FakeRuntimeConfigStorage()
        server.storage = fake_storage
        server.PROXY_API_KEY_RECORDS = []
        client = server.app.test_client()
        with client.session_transaction() as session:
            session["_proxy_authed"] = True

        create_response = client.post("/debug/proxy-keys", json={"action": "create", "name": "NEWAPI"})
        create_payload = create_response.get_json()
        generated_key = create_payload["generated_key"]
        record = server.PROXY_API_KEY_RECORDS[0]

        self.assertEqual(fake_storage.saved_key, "runtime_config")
        self.assertIn("proxy_api_key_records", fake_storage.saved_payload)
        self.assertEqual(fake_storage.saved_payload["proxy_api_key_records"][0]["id"], record["id"])
        self.assertEqual(fake_storage.saved_payload["proxy_api_key_records"][0]["key_hash"], record["key_hash"])
        self.assertNotIn(generated_key, str(fake_storage.saved_payload))
        self.assertRegex(generated_key, r"^sk-[A-Za-z0-9]{48}$")

    def test_saving_public_config_payload_does_not_drop_managed_proxy_keys(self):
        server = self.load_server_with_keys("")
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        server.PROXY_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.json"
        server.PROXY_API_KEY_RECORDS = []
        client = server.app.test_client()
        with client.session_transaction() as session:
            session["_proxy_authed"] = True

        create_response = client.post("/debug/proxy-keys", json={"action": "create", "name": "NEWAPI"})
        generated_key = create_response.get_json()["generated_key"]

        config_payload = client.get("/debug/config").get_json()["config"]
        config_payload["request_timeout"] = 601
        save_response = client.post("/debug/config", json=config_payload)

        self.assertEqual(save_response.status_code, 200)
        ok_response = client.get(
            "/v1",
            headers={"Accept": "application/json", "Authorization": f"Bearer {generated_key}"},
        )
        self.assertEqual(ok_response.status_code, 200)

    def test_saving_public_config_payload_persists_stream_first_event_timeout(self):
        server = self.load_server_with_keys("")
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        server.PROXY_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.json"
        client = server.app.test_client()
        with client.session_transaction() as session:
            session["_proxy_authed"] = True

        config_payload = client.get("/debug/config").get_json()["config"]
        config_payload["stream_first_event_timeout_seconds"] = 650
        save_response = client.post("/debug/config", json=config_payload)

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(server.STREAM_FIRST_EVENT_TIMEOUT_SECONDS, 650)
        saved_payload = __import__("json").loads(server.PROXY_CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved_payload["stream_first_event_timeout_seconds"], 650)

    def test_saving_public_config_payload_keeps_stream_first_event_timeout_below_request_timeout(self):
        server = self.load_server_with_keys("")
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        server.PROXY_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.json"
        client = server.app.test_client()
        with client.session_transaction() as session:
            session["_proxy_authed"] = True

        config_payload = client.get("/debug/config").get_json()["config"]
        config_payload["request_timeout"] = 180
        config_payload["stream_first_event_timeout_seconds"] = 20
        save_response = client.post("/debug/config", json=config_payload)

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(server.REQUEST_TIMEOUT, 180)
        self.assertEqual(server.STREAM_FIRST_EVENT_TIMEOUT_SECONDS, 20)
        saved_payload = __import__("json").loads(server.PROXY_CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved_payload["request_timeout"], 180)
        self.assertEqual(saved_payload["stream_first_event_timeout_seconds"], 20)

    def test_saving_public_config_payload_persists_request_timeout_below_30(self):
        server = self.load_server_with_keys("")
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        server.PROXY_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.json"
        client = server.app.test_client()
        with client.session_transaction() as session:
            session["_proxy_authed"] = True

        config_payload = client.get("/debug/config").get_json()["config"]
        config_payload["request_timeout"] = 5
        save_response = client.post("/debug/config", json=config_payload)

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(server.REQUEST_TIMEOUT, 5)
        saved_payload = __import__("json").loads(server.PROXY_CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved_payload["request_timeout"], 5)

    def test_initialize_runtime_config_bootstraps_disk_payload_into_mysql_storage(self):
        server = self.load_server_with_keys("")
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        server.PROXY_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.json"
        server.PROXY_REMOTE_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.remote.json"
        server.PROXY_API_KEY_RECORDS = []
        server.PROXY_POOLS = []
        server.MODEL_CAPABILITIES_TEXT = ""
        payload = {
            "proxy_api_key_records": [
                {
                    "id": "pak_demo",
                    "name": "NEWAPI",
                    "key": "sk-bootstrap-secret",
                    "enabled": True,
                    "created_at": "2026-05-05 00:00:00",
                    "updated_at": "2026-05-05 00:00:00",
                }
            ],
            "pools": [
                {
                    "name": "nv",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-1"}],
                }
            ],
            "request_timeout": 30,
        }
        server.PROXY_CONFIG_PATH.write_text(
            __import__("json").dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        fake_storage = FakeRuntimeConfigStorage()
        server.storage = fake_storage
        server.STORAGE_DB_LABEL = "mysql://demo"

        source = server.initialize_runtime_config()

        self.assertEqual(source, "disk")
        self.assertEqual(fake_storage.saved_key, "runtime_config")
        self.assertIsNotNone(fake_storage.saved_payload)
        self.assertEqual(fake_storage.saved_payload["proxy_api_key_records"][0]["id"], "pak_demo")
        self.assertEqual(fake_storage.saved_payload["pools"][0]["name"], "nv")
        self.assertEqual(server.ACTIVE_RUNTIME_CONFIG_PATH, server.PROXY_CONFIG_PATH)

    def test_initialize_runtime_config_prefers_newer_remote_disk_snapshot_when_storage_unavailable(self):
        server = self.load_server_with_keys("")
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        server.PROXY_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.json"
        server.PROXY_REMOTE_CONFIG_PATH = Path(temp_dir.name) / "proxy-config.remote.json"
        server.storage = None
        server.PROXY_POOLS = []
        server.PROXY_API_KEY_RECORDS = []

        stale_payload = {
            "pools": [
                {
                    "name": "old-juece",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://open.juece.cloud/v1"],
                    "keys": [{"key": "old-key"}],
                }
            ],
            "request_timeout": 30,
        }
        fresh_payload = {
            "pools": [
                {
                    "name": "nv",
                    "enabled": True,
                    "priority": 100,
                    "urls": ["https://integrate.api.nvidia.com/v1"],
                    "keys": [{"key": "nv-key-1"}],
                }
            ],
            "request_timeout": 30,
        }
        server.PROXY_CONFIG_PATH.write_text(
            __import__("json").dumps(stale_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        server.PROXY_REMOTE_CONFIG_PATH.write_text(
            __import__("json").dumps(fresh_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        os.utime(server.PROXY_CONFIG_PATH, (1_000_000_000, 1_000_000_000))
        os.utime(server.PROXY_REMOTE_CONFIG_PATH, (1_000_000_100, 1_000_000_100))

        source = server.initialize_runtime_config()

        self.assertEqual(source, "disk")
        self.assertEqual(server.ACTIVE_RUNTIME_CONFIG_PATH, server.PROXY_REMOTE_CONFIG_PATH)
        self.assertEqual(server.PROXY_POOLS[0]["name"], "nv")
        self.assertEqual(server.build_runtime_config_payload()["config_path"], str(server.PROXY_REMOTE_CONFIG_PATH))


if __name__ == "__main__":
    unittest.main()
