from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from app.runtime import NemoGuardrailsRuntime


@pytest.mark.asyncio
async def test_default_nemo_profile_passes_and_blocks():
    profile = Path(__file__).parent.parent / "profiles" / "model-io-default-v1"
    runtime = NemoGuardrailsRuntime(profile)

    passed = await runtime.check("request", "Summarize this document.", [])
    blocked = await runtime.check("response", "api_key=abcdefghijklmnop", [])
    pii = await runtime.check("request", "SSN: 123-45-6789", [])

    assert passed.status == "PASSED"
    assert blocked.status == "BLOCKED"
    assert pii.status == "BLOCKED"


@pytest.mark.asyncio
async def test_nvidia_content_safety_and_topic_control_pipeline(monkeypatch):
    class NvidiaHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            size = int(self.headers.get("content-length", "0"))
            request = json.loads(self.rfile.read(size))
            prompt = "\n".join(
                str(message.get("content", ""))
                for message in request.get("messages", [])
            )
            model = request.get("model")
            if model == "test/topic-control":
                verdict = "off-topic" if "force-topic-block" in prompt else "on-topic"
            else:
                safety = "unsafe" if "force-content-block" in prompt else "safe"
                verdict = json.dumps(
                    {
                        "User Safety": safety,
                        "Response Safety": safety,
                    }
                )
            payload = json.dumps(
                {
                    "id": "nvidia-guardrail-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": verdict,
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), NvidiaHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("TEST_NVIDIA_API_KEY", "test-key")
    profile = Path(__file__).parent.parent / "profiles" / "model-io-default-v1"

    try:
        runtime = NemoGuardrailsRuntime(
            profile,
            nvidia_base_url=f"http://127.0.0.1:{server.server_port}/v1",
            content_safety_model="test/content-safety",
            topic_control_model="test/topic-control",
            nvidia_api_key_env_var="TEST_NVIDIA_API_KEY",
        )

        safe_input = await runtime.check("request", "Summarize this document.", [])
        unsafe_input = await runtime.check("request", "force-content-block", [])
        off_topic_input = await runtime.check("request", "force-topic-block", [])
        safe_output = await runtime.check(
            "response",
            "Here is a concise summary.",
            [{"role": "user", "content": "Summarize this document."}],
        )
        unsafe_output = await runtime.check(
            "response",
            "force-content-block",
            [{"role": "user", "content": "Summarize this document."}],
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    models = runtime._rails.config.models
    assert [(model.type, model.engine) for model in models] == [
        ("content_safety", "nim"),
        ("topic_control", "nim"),
    ]
    assert runtime._rails.config.rails.input.flows[-2:] == [
        "content safety check input $model=content_safety",
        "topic safety check input $model=topic_control",
    ]
    assert runtime._rails.config.rails.output.flows[-1] == (
        "content safety check output $model=content_safety"
    )
    assert safe_input.status == "PASSED"
    assert unsafe_input.status == "BLOCKED"
    assert off_topic_input.status == "BLOCKED"
    assert safe_output.status == "PASSED"
    assert unsafe_output.status == "BLOCKED"
