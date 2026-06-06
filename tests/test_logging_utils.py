from local_proxy.upstream.logging_utils import summarize_attempt_routes


def test_summarize_attempt_routes_handles_list_urls() -> None:
    attempt_urls, attempt_chain = summarize_attempt_routes(
        [
            {
                "upstream_url": [
                    "https://opencode.ai/zen/v1/chat/completions",
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                ]
            },
            {
                "upstream_url": "https://integrate.api.nvidia.com/v1/chat/completions",
            },
        ]
    )

    assert attempt_urls == [
        "https://opencode.ai/zen/v1/chat/completions | https://integrate.api.nvidia.com/v1/chat/completions",
        "https://integrate.api.nvidia.com/v1/chat/completions",
    ]
    assert attempt_chain == (
        "https://opencode.ai/zen/v1/chat/completions | https://integrate.api.nvidia.com/v1/chat/completions"
        " -> https://integrate.api.nvidia.com/v1/chat/completions"
    )
