#!/usr/bin/env python3
"""Local-only VinBank Blue Team chat demo.

Run from the repository root:
    .venv/bin/python ui-demo/app.py

The browser talks only to this local server.  API keys remain in ``.env`` and
are used by the existing Blue/OpenRouter runtime on the server side.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.agent import create_blue_agent
from assignment.pipeline import build_production_plugins
from core.config import blue_provider_label, get_openrouter_api_key
from core.utils import chat_with_agent

STATIC_DIR = Path(__file__).resolve().parent / "static"
INPUT_BLOCK_MARKERS = (
    "i can't process instructions that attempt to override",
    "i can only help with vinbank banking-related questions",
)


class BlueChatService:
    """One local Blue agent instance shared by the UI server."""

    def __init__(self) -> None:
        self.plugins = build_production_plugins(use_llm_judge=False)
        self.agent, self.runner = create_blue_agent(self.plugins)
        # The SDK default can wait several minutes when a provider is down.  A
        # demo should return control promptly instead of leaving its Send button
        # disabled indefinitely.
        self.runner.client_kwargs["timeout"] = 12.0

    def health(self) -> dict:
        return {
            "provider": blue_provider_label(),
            "ready": bool(get_openrouter_api_key()),
            "mode": "Blue Team • Guardrails enabled",
        }

    def chat(self, message: str) -> dict:
        try:
            response, _ = asyncio.run(self._chat_live_with_timeout(message))
            mode = "live"
        except Exception:
            response = self._fallback_reply(message)
            mode = "fallback"
        response = response or "I couldn't generate a response. Please try again."
        lower = response.casefold()
        if lower.startswith("rate limit exceeded"):
            layer = "rate_limiter"
            status = "Blocked before the model"
        elif any(marker in lower for marker in INPUT_BLOCK_MARKERS):
            layer = "input_guardrail"
            status = "Blocked before the model"
        elif "[redacted]" in lower:
            layer = "output_guardrail"
            status = "Sensitive content redacted"
        else:
            layer = None
            status = (
                "Passed Blue guardrails"
                if mode == "live"
                else "Local demo fallback — OpenRouter did not respond"
            )
        return {"response": response, "layer": layer, "status": status, "mode": mode}

    async def _chat_live_with_timeout(self, message: str):
        """Run the blocking SDK call away from the HTTP thread with a hard cap."""
        return await asyncio.wait_for(
            asyncio.to_thread(
                lambda: asyncio.run(chat_with_agent(self.agent, self.runner, message))
            ),
            timeout=15,
        )

    @staticmethod
    def _fallback_reply(message: str) -> str:
        """Useful, non-transactional local reply when the live model is unavailable."""
        text = message.casefold()
        if any(term in text for term in ("số dư", "so du", "balance", "tài khoản", "tai khoan", "account")):
            return (
                "Chế độ demo local: Bạn có thể xem số dư trong ứng dụng VinBank, "
                "Internet Banking hoặc tại ATM. Không nhập mật khẩu hay thông tin "
                "tài khoản thật vào khung chat demo."
            )
        if any(term in text for term in ("tiết kiệm", "tiet kiem", "lãi suất", "lai suat", "savings", "interest")):
            return (
                "Chế độ demo local: Lãi suất tiết kiệm thay đổi theo kỳ hạn và sản phẩm. "
                "Hãy xem biểu lãi suất chính thức trong ứng dụng hoặc liên hệ VinBank "
                "để nhận thông tin hiện hành."
            )
        if any(term in text for term in ("chuyển tiền", "chuyen tien", "transfer", "transaction")):
            return (
                "Chế độ demo local: Bạn có thể tạo lệnh chuyển tiền trong ứng dụng VinBank "
                "sau khi kiểm tra người nhận và số tiền. Demo này không thực hiện giao dịch."
            )
        return (
            "Chế độ demo local: Tôi hỗ trợ các chủ đề tài khoản, chuyển tiền, tiết kiệm, "
            "khoản vay và thẻ tín dụng. Blue model live hiện chưa phản hồi."
        )


class DemoHandler(BaseHTTPRequestHandler):
    """Serve the static client and a tiny same-origin JSON API."""

    service: BlueChatService

    def log_message(self, _format: str, *_args) -> None:
        """Avoid logging user chat content to the terminal."""

    def _send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, filename: str, content_type: str) -> None:
        path = STATIC_DIR / filename
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required BaseHTTPRequestHandler name
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_file("index.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self._send_file("app.js", "application/javascript; charset=utf-8")
        elif path == "/styles.css":
            self._send_file("styles.css", "text/css; charset=utf-8")
        elif path == "/api/health":
            self._send_json(HTTPStatus.OK, self.service.health())
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - required BaseHTTPRequestHandler name
        if urlparse(self.path).path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 12_000:
                raise ValueError("Message must be between 1 and 12000 bytes.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            message = payload.get("message", "")
            if not isinstance(message, str) or not message.strip():
                raise ValueError("Please enter a message.")
            result = self.service.chat(message.strip())
            self._send_json(HTTPStatus.OK, result)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            # Do not expose provider errors, stack traces, or configuration details.
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": (
                        "The Blue model is unavailable. Check your local OpenRouter key "
                        "and network connection, then try again."
                    )
                },
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local VinBank UI demo")
    parser.add_argument("--host", default="127.0.0.1", help="Default: loopback only")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("For safety, this demo may only bind to localhost.")

    DemoHandler.service = BlueChatService()
    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"VinBank demo ready at http://{args.host}:{args.port}")
    print("Blue pipeline: rate limit → input guardrail → LLM → output guardrail")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nVinBank demo stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
