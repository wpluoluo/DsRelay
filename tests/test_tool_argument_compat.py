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


if __name__ == "__main__":
    unittest.main()
