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

TOOLSEARCH_TOOL_SCHEMAS = {
    "ToolSearch": {
        "required": [],
        "required_any": [("queries", "tool_names")],
        "properties": ["queries", "tool_names"],
        "additional_properties": False,
        "property_types": {
            "queries": "array",
            "tool_names": "array",
        },
    }
}

SKILL_TOOL_SCHEMAS = {
    "Skill": {
        "required": [],
        "required_any": [("skill", "command")],
        "properties": ["skill", "command"],
        "additional_properties": False,
        "property_types": {
            "skill": "string",
            "command": "string",
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

    def test_stream_tool_call_list_index_is_coerced(self):
        choice_states = {}
        chunk = {
            "id": "chatcmpl-list-index",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": ["0"],
                    "delta": {
                        "tool_calls": [
                            {
                                "index": [0],
                                "id": "call_read",
                                "type": "function",
                                "function": {
                                    "name": "Grep",
                                    "arguments": "{\"query\":\"needle\"}",
                                },
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }

        normalized_line, _, repaired, event = normalize_sse_line(
            "data: " + json.dumps(chunk),
            choice_states,
            GREP_TOOL_SCHEMAS,
        )

        self.assertIsNotNone(normalized_line)
        self.assertGreaterEqual(repaired, 1)
        self.assertEqual(event["choices"][0]["index"], 0)
        self.assertEqual(event["choices"][0]["delta"]["tool_calls"][0]["index"], 0)
        self.assertEqual(
            json.loads(event["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"]),
            {"pattern": "needle"},
        )

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

    def test_toolsearch_query_alias_is_normalized_to_queries_array(self):
        normalized, modified = normalize_tool_arguments_payload(
            "ToolSearch",
            {"query": "browser automation"},
            TOOLSEARCH_TOOL_SCHEMAS,
        )

        self.assertTrue(modified)
        self.assertEqual(normalized, {"queries": ["browser automation"]})

    def test_toolsearch_tool_names_alias_is_normalized_to_array(self):
        normalized, modified = normalize_tool_arguments_payload(
            "ToolSearch",
            {"toolNames": "automation_update, list_threads"},
            TOOLSEARCH_TOOL_SCHEMAS,
        )

        self.assertTrue(modified)
        self.assertEqual(normalized, {"tool_names": ["automation_update", "list_threads"]})

    def test_empty_toolsearch_call_is_suppressed_before_client_validation(self):
        tool_calls = [
            {
                "id": "call_empty_toolsearch",
                "type": "function",
                "function": {
                    "name": "ToolSearch",
                    "arguments": "{}",
                },
            }
        ]

        normalized_calls, repaired = normalize_tool_call_list(tool_calls, TOOLSEARCH_TOOL_SCHEMAS)

        self.assertGreater(repaired, 0)
        self.assertEqual(normalized_calls, [])

    def test_stream_toolsearch_name_without_arguments_does_not_end_as_tool_call(self):
        choice_states = {}
        name_only = {
            "id": "chatcmpl-toolsearch",
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
                                "id": "call_toolsearch",
                                "type": "function",
                                "function": {"name": "ToolSearch"},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }
        terminal = {
            "id": "chatcmpl-toolsearch",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
        }

        normalized_line, _, repaired, event = normalize_sse_line(
            "data: " + json.dumps(name_only),
            choice_states,
            TOOLSEARCH_TOOL_SCHEMAS,
        )
        self.assertIsNone(normalized_line)
        self.assertEqual(event["choices"], [])
        self.assertGreaterEqual(repaired, 0)

        normalized_terminal, _, terminal_repairs, terminal_event = normalize_sse_line(
            "data: " + json.dumps(terminal),
            choice_states,
            TOOLSEARCH_TOOL_SCHEMAS,
        )
        self.assertGreaterEqual(terminal_repairs, 0)
        self.assertIsNotNone(normalized_terminal)
        self.assertEqual(terminal_event["choices"][0]["finish_reason"], "stop")
        self.assertNotIn("tool_calls", json.dumps(terminal_event))

    def test_skill_name_alias_is_normalized(self):
        normalized, modified = normalize_tool_arguments_payload(
            "Skill",
            {"name": "clear"},
            SKILL_TOOL_SCHEMAS,
        )

        self.assertTrue(modified)
        self.assertEqual(normalized, {"skill": "clear"})

    def test_empty_skill_call_is_suppressed_before_client_validation(self):
        tool_calls = [
            {
                "id": "call_empty_skill",
                "type": "function",
                "function": {
                    "name": "Skill",
                    "arguments": "{}",
                },
            }
        ]

        normalized_calls, repaired = normalize_tool_call_list(tool_calls, SKILL_TOOL_SCHEMAS)

        self.assertGreater(repaired, 0)
        self.assertEqual(normalized_calls, [])

    def test_stream_skill_name_without_arguments_does_not_end_as_tool_call(self):
        choice_states = {}
        name_only = {
            "id": "chatcmpl-skill",
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
                                "id": "call_skill",
                                "type": "function",
                                "function": {"name": "Skill"},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }
        terminal = {
            "id": "chatcmpl-skill",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
        }

        normalized_line, _, repaired, event = normalize_sse_line(
            "data: " + json.dumps(name_only),
            choice_states,
            SKILL_TOOL_SCHEMAS,
        )
        self.assertIsNone(normalized_line)
        self.assertEqual(event["choices"], [])
        self.assertGreaterEqual(repaired, 0)

        normalized_terminal, _, terminal_repairs, terminal_event = normalize_sse_line(
            "data: " + json.dumps(terminal),
            choice_states,
            SKILL_TOOL_SCHEMAS,
        )
        self.assertGreaterEqual(terminal_repairs, 0)
        self.assertIsNotNone(normalized_terminal)
        self.assertEqual(terminal_event["choices"][0]["finish_reason"], "stop")
        self.assertNotIn("tool_calls", json.dumps(terminal_event))

    def test_stream_visible_text_then_empty_skill_call_keeps_text_and_stops(self):
        choice_states = {}
        text_chunk = {
            "id": "chatcmpl-skill-text",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "好，检查一下当前组件库的完成状态。"},
                    "finish_reason": None,
                }
            ],
        }
        name_only = {
            "id": "chatcmpl-skill-text",
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
                                "id": "call_skill",
                                "type": "function",
                                "function": {"name": "Skill"},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ],
        }
        terminal = {
            "id": "chatcmpl-skill-text",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "demo",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
        }

        normalized_text_line, _, _, text_event = normalize_sse_line(
            "data: " + json.dumps(text_chunk),
            choice_states,
            SKILL_TOOL_SCHEMAS,
        )
        self.assertIsNotNone(normalized_text_line)
        self.assertEqual(
            text_event["choices"][0]["delta"]["content"],
            "好，检查一下当前组件库的完成状态。",
        )

        normalized_name_line, _, name_repairs, name_event = normalize_sse_line(
            "data: " + json.dumps(name_only),
            choice_states,
            SKILL_TOOL_SCHEMAS,
        )
        self.assertIsNone(normalized_name_line)
        self.assertEqual(name_event["choices"], [])
        self.assertGreaterEqual(name_repairs, 0)

        normalized_terminal, _, terminal_repairs, terminal_event = normalize_sse_line(
            "data: " + json.dumps(terminal),
            choice_states,
            SKILL_TOOL_SCHEMAS,
        )
        self.assertGreaterEqual(terminal_repairs, 0)
        self.assertIsNotNone(normalized_terminal)
        self.assertEqual(terminal_event["choices"][0]["finish_reason"], "stop")
        self.assertNotIn("tool_calls", json.dumps(terminal_event))


if __name__ == "__main__":
    unittest.main()
