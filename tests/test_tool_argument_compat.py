import json
import unittest

from local_proxy.compat.tools import normalize_tool_arguments_payload, normalize_tool_call_list


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


if __name__ == "__main__":
    unittest.main()
