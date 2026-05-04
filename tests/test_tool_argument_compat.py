import json
import unittest

from local_proxy.compat.tools import normalize_sse_line, normalize_tool_arguments_payload, normalize_tool_call_list


BASH_TOOL_SCHEMAS = {
    "Bash": {
        "required": ["command"],
        "properties": ["command"],
        "additional_properties": False,
        "property_types": {"command": "string"},
    }
}

GREP_TOOL_SCHEMAS = {
    "Grep": {
        "required": ["pattern"],
        "properties": ["pattern", "path", "include"],
        "additional_properties": False,
        "property_types": {
            "pattern": "string",
            "path": "string",
            "include": "string",
        },
    }
}

TASK_TOOL_SCHEMAS = {
    "Task": {
        "required": ["task_id", "run_in_background"],
        "properties": ["task_id", "run_in_background"],
        "additional_properties": False,
        "property_types": {
            "task_id": "string",
            "run_in_background": "boolean",
        },
    }
}

TASKSTOP_TOOL_SCHEMAS = {
    "TaskStop": {
        "required": ["task_id"],
        "properties": ["task_id"],
        "additional_properties": False,
        "property_types": {
            "task_id": "string",
        },
    }
}


class ToolArgumentCompatTests(unittest.TestCase):
    def test_bash_alias_argument_is_normalized_to_command(self):
        normalized, modified = normalize_tool_arguments_payload(
            "Bash",
            {"bash_command": "pwd"},
            BASH_TOOL_SCHEMAS,
        )

        self.assertTrue(modified)
        self.assertEqual(normalized, {"command": "pwd"})

    def test_empty_bash_tool_call_is_suppressed_before_client_validation(self):
        tool_calls = [
            {
                "id": "call_empty_bash",
                "type": "function",
                "function": {
                    "name": "Bash",
                    "arguments": "{}",
                },
            }
        ]

        normalized_calls, repaired = normalize_tool_call_list(tool_calls, BASH_TOOL_SCHEMAS)

        self.assertGreater(repaired, 0)
        self.assertEqual(normalized_calls, [])

    def test_non_empty_bash_tool_call_keeps_required_command(self):
        tool_calls = [
            {
                "id": "call_bash",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": json.dumps({"cmd": "ls -la"}),
                },
            }
        ]

        normalized_calls, repaired = normalize_tool_call_list(tool_calls, BASH_TOOL_SCHEMAS)

        self.assertGreater(repaired, 0)
        self.assertEqual(len(normalized_calls), 1)
        self.assertEqual(normalized_calls[0]["function"]["name"], "Bash")
        self.assertEqual(
            json.loads(normalized_calls[0]["function"]["arguments"]),
            {"command": "ls -la"},
        )

    def test_stream_bash_name_without_arguments_is_not_forwarded_as_partial_tool_call(self):
        choice_states = {}
        name_only = {
            "id": "chatcmpl-bash",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_bash",
                                "type": "function",
                                "function": {"name": "Bash"},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }
        terminal = {
            "id": "chatcmpl-bash",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
        }

        normalized_line, _, repaired, event = normalize_sse_line(
            "data: " + json.dumps(name_only),
            choice_states,
            BASH_TOOL_SCHEMAS,
        )
        self.assertIsNone(normalized_line)
        self.assertEqual(event["choices"], [])
        self.assertGreaterEqual(repaired, 0)

        normalized_terminal, _, terminal_repairs, terminal_event = normalize_sse_line(
            "data: " + json.dumps(terminal),
            choice_states,
            BASH_TOOL_SCHEMAS,
        )
        self.assertGreaterEqual(terminal_repairs, 0)
        self.assertIsNotNone(normalized_terminal)
        self.assertEqual(terminal_event["choices"][0]["finish_reason"], "stop")
        self.assertNotIn("tool_calls", json.dumps(terminal_event))

    def test_grep_query_alias_is_normalized_to_pattern(self):
        normalized, modified = normalize_tool_arguments_payload(
            "Grep",
            {"query": "InputValidationError"},
            GREP_TOOL_SCHEMAS,
        )

        self.assertTrue(modified)
        self.assertEqual(normalized, {"pattern": "InputValidationError"})

    def test_grep_regex_alias_is_normalized_to_pattern_with_path(self):
        normalized, modified = normalize_tool_arguments_payload(
            "Grep",
            {"regex": "InputValidationError", "path": "local_proxy"},
            GREP_TOOL_SCHEMAS,
        )

        self.assertTrue(modified)
        self.assertEqual(
            normalized,
            {"pattern": "InputValidationError", "path": "local_proxy"},
        )

    def test_empty_grep_tool_call_is_suppressed_before_client_validation(self):
        tool_calls = [
            {
                "id": "call_empty_grep",
                "type": "function",
                "function": {
                    "name": "Grep",
                    "arguments": "{}",
                },
            }
        ]

        normalized_calls, repaired = normalize_tool_call_list(tool_calls, GREP_TOOL_SCHEMAS)

        self.assertGreater(repaired, 0)
        self.assertEqual(normalized_calls, [])

    def test_metadata_only_grep_tool_call_is_suppressed_before_client_validation(self):
        tool_calls = [
            {
                "id": "call_metadata_grep",
                "type": "function",
                "function": {
                    "name": "Grep",
                    "arguments": json.dumps({"description": "search errors"}),
                },
            }
        ]

        normalized_calls, repaired = normalize_tool_call_list(tool_calls, GREP_TOOL_SCHEMAS)

        self.assertGreater(repaired, 0)
        self.assertEqual(normalized_calls, [])

    def test_path_only_grep_tool_call_is_suppressed_instead_of_becoming_pattern(self):
        tool_calls = [
            {
                "id": "call_path_only_grep",
                "type": "function",
                "function": {
                    "name": "Grep",
                    "arguments": json.dumps({"path": "local_proxy"}),
                },
            }
        ]

        normalized_calls, repaired = normalize_tool_call_list(tool_calls, GREP_TOOL_SCHEMAS)

        self.assertGreater(repaired, 0)
        self.assertEqual(normalized_calls, [])

    def test_rg_alias_uses_grep_schema_and_pattern_aliases(self):
        tool_calls = [
            {
                "id": "call_rg",
                "type": "function",
                "function": {
                    "name": "rg",
                    "arguments": json.dumps({"search": "InputValidationError"}),
                },
            }
        ]

        normalized_calls, repaired = normalize_tool_call_list(tool_calls, GREP_TOOL_SCHEMAS)

        self.assertGreater(repaired, 0)
        self.assertEqual(len(normalized_calls), 1)
        self.assertEqual(normalized_calls[0]["function"]["name"], "Grep")
        self.assertEqual(
            json.loads(normalized_calls[0]["function"]["arguments"]),
            {"pattern": "InputValidationError"},
        )

    def test_task_tool_keeps_required_run_in_background(self):
        normalized, modified = normalize_tool_arguments_payload(
            "Task",
            {"task_id": "bca9cjr2x"},
            TASK_TOOL_SCHEMAS,
        )

        self.assertTrue(modified)
        self.assertEqual(normalized["task_id"], "bca9cjr2x")
        self.assertIn("run_in_background", normalized)
        self.assertIs(normalized["run_in_background"], False)

    def test_taskstop_tool_does_not_inject_run_in_background(self):
        normalized, modified = normalize_tool_arguments_payload(
            "TaskStop",
            {"task_id": "bca9cjr2x"},
            TASKSTOP_TOOL_SCHEMAS,
        )

        self.assertFalse("run_in_background" in normalized)
        self.assertEqual(normalized, {"task_id": "bca9cjr2x"})


if __name__ == "__main__":
    unittest.main()
