"""Isolated loopback inference transport. No DB, tools, workflow or evidence imports."""

from __future__ import annotations

import argparse
import hmac
import http.client
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .investigator_shadow import PROMPT, canonical, fake_proposal, generation_schema


class Runner:
    def __init__(self, config: dict, *, response_observer=None, credential_loader=None):
        self.config = config
        # Optional private evaluation sink, never a model tool or public log.
        self.response_observer = response_observer
        self.credential_loader = credential_loader
        self.transport_diagnostics = {}
        self.lock = threading.Lock()
        self.used = 0
        self.mode = config.get("mode")
        if self.mode == "fake":
            self.model = "deterministic-fake-1"
            self.limit = 100
        elif self.mode == "openai":
            from .investigator_shadow_openai import validate_config

            validate_config(config)
            self.model, self.limit = config["model"], config["max_requests"]
        elif self.mode == "ollama":
            required = {
                "mode",
                "endpoint",
                "model",
                "synthetic_only",
                "approval_reference",
                "max_requests",
                "max_input_tokens",
                "max_output_tokens",
                "timeout_seconds",
            }
            if (
                set(config) != required
                or config["synthetic_only"] is not True
                or not config["approval_reference"]
            ):
                raise ValueError("explicit synthetic resource approval required")
            parsed = urlparse(config["endpoint"])
            if (
                parsed.scheme != "http"
                or parsed.hostname != "127.0.0.1"
                or parsed.path != "/api/chat"
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "only the approved local Ollama transport is supported"
                )
            self.model = config["model"]
            if not isinstance(self.model, str) or not 1 <= len(self.model) <= 120:
                raise ValueError("operator must select a preinstalled model")
            for key, bound in (
                ("max_requests", 20),
                ("max_input_tokens", 32768),
                ("max_output_tokens", 2048),
                ("timeout_seconds", 30),
            ):
                if type(config[key]) is not int or not 1 <= config[key] <= bound:
                    raise ValueError("finite bounded resource configuration required")
            self.limit = config["max_requests"]
        else:
            raise ValueError("inference disabled: explicit mode required")

    def generate(self, context: dict) -> dict:
        if (
            context.get("synthetic_only") is not True
            or len(canonical(context).encode()) > 24000
        ):
            raise ValueError("bounded synthetic input required")
        with self.lock:
            if self.used >= self.limit:
                raise ValueError("approved request budget exhausted")
            self.used += 1
        started = time.monotonic()
        if self.mode == "fake":
            proposal = fake_proposal(context)
            if self.response_observer is not None:
                self.response_observer(canonical(proposal).encode())
            usage = None
        elif self.mode == "openai":
            from .investigator_shadow_openai import generate

            proposal, usage = generate(
                self.config,
                context,
                self.credential_loader,
                self.response_observer,
                self.transport_diagnostics,
            )
        else:
            # Count input bytes conservatively as a token upper bound. No tokenizer dependency.
            content = canonical(context)
            schema = generation_schema(context)
            system = PROMPT + canonical(schema)
            if len((content + system).encode()) > self.config["max_input_tokens"]:
                raise ValueError("approved input-token upper bound exceeded")
            target = urlparse(self.config["endpoint"])
            transport = http.client.HTTPConnection(
                "127.0.0.1", target.port or 80, timeout=self.config["timeout_seconds"]
            )
            try:
                transport.request(
                    "POST",
                    "/api/chat",
                    body=canonical(
                        {
                            "model": self.model,
                            "stream": False,
                            "think": False,
                            "format": schema,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": content},
                            ],
                            "options": {
                                "num_predict": self.config["max_output_tokens"],
                                "num_ctx": self.config["max_input_tokens"]
                                + self.config["max_output_tokens"],
                                "temperature": 0,
                            },
                            "keep_alive": 0,
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                )
                response = transport.getresponse()
                raw = response.read(32001)
                if self.response_observer is not None:
                    self.response_observer(raw)
                if response.status != 200 or len(raw) > 32000:
                    raise ValueError("model response unavailable or oversized")
                data = json.loads(raw)
                if (
                    data.get("model") != self.model
                    or data.get("done") is not True
                    or data["message"].get("tool_calls")
                ):
                    raise ValueError("model identity/completion/tool violation")
                proposal = json.loads(data["message"]["content"])
                usage = {
                    "input_tokens": data.get("prompt_eval_count"),
                    "output_tokens": data.get("eval_count"),
                }
            finally:
                transport.close()
        return {
            "provider": self.mode,
            "model": self.model,
            "proposal": proposal,
            "usage": usage,
            "cost": None,
            "latency_ms": round((time.monotonic() - started) * 1000),
            **(
                {"transport_diagnostics": dict(self.transport_diagnostics)}
                if self.mode == "openai"
                else {}
            ),
        }


def build_handler(runner: Runner, token: str):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/generate" or not hmac.compare_digest(
                self.headers.get("Authorization", ""), "Bearer " + token
            ):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 24000:
                    raise ValueError("bounded context required")
                result = runner.generate(json.loads(self.rfile.read(length)))
                body = canonical(result).encode()
                self.send_response(200)
            except TimeoutError:
                body = b'{"failure":"TIMEOUT"}'
                self.send_response(200)
            except Exception:  # noqa: BLE001 - never log input/provider bodies
                body = b'{"failure":"FAILED"}'
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    return Handler


def main():
    # Operator starts with env -i. Reject inherited custody, without printing values.
    if any(
        any(
            word in key
            for word in ("DATABASE", "DSN", "BELVO", "STP_", "OPENAI", "ANTHROPIC")
        )
        for key in os.environ
    ):
        raise RuntimeError("runner environment contains forbidden custody")
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8087)
    args = parser.parse_args()
    runner = Runner(json.loads(os.environ.get("OLIN_SHADOW_RUNNER_CONFIG", "{}")))
    token = os.environ.get("OLIN_SHADOW_RUNNER_TOKEN", "")
    if len(token) < 24:
        raise RuntimeError("dedicated runner transport token required")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), build_handler(runner, token))
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
