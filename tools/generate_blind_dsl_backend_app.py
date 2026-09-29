from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import generate_blind_dsl_static_app as static_gen


EXPECTED_FILES = {
    "package.json",
    "server.js",
    "public/index.html",
    "public/styles.css",
    "public/app.js",
}


def behavior_requirements() -> str:
    marker = "Requirements:\n"
    tail_marker = "\nRequested visual variant:"
    try:
        return static_gen.PROMPT.split(marker, 1)[1].split(tail_marker, 1)[0].strip()
    except IndexError as exc:
        raise RuntimeError("Could not extract base behavior requirements from static generator prompt") from exc


PROMPT = """You are generating a blind DetoxBench candidate web app from a public DSL contract only.

This experiment changes only the generated application substrate. Build a minimal
frontend plus a local backend server with persistent storage. Do not assume
access to hidden evaluator scenarios. Implement the public behavior declared by
the contract and any public scenario examples included below, not a guessed
hidden test script.

Create a runnable Express + JSON-file storage app with exactly these files:
- package.json
- server.js
- public/index.html
- public/styles.css
- public/app.js

Backend substrate requirements:
- package.json must define "start": "node server.js" and depend on "express".
- server.js must listen on process.env.PORT and should bind to process.env.HOST
  or "127.0.0.1". Do not hard-code a port.
- Serve public/index.html and the other frontend assets from the Express server.
- Keep durable workflow state in JSON files under process.env.DETOX_STORAGE_DIR
  when it is set, otherwise under a local data directory next to server.js.
- All user-facing state mutations must go through browser fetch/XHR calls to
  the local backend. The frontend may mirror state for rendering and
  window.__DETOX_STATE__, but reload must hydrate from backend storage.
- Use backend state endpoints that do not collide with runtime.services
  endpoints from the DSL contract. Prefer paths under /__app/.
- Isolate browser contexts the same way the existing static localStorage
  substrate does: if a request has no app session cookie, create a new session
  id and initialize that session from state.initial. A real browser reload in
  the same context must keep the same cookie and persisted state. A fresh
  browser context with no cookies must start from a fresh copy of initial state.
- Implement POST /__detox/reset to clear the JSON storage directory and in-memory
  session cache. This endpoint is for the runtime harness before scoring; the
  evaluator still scores only through browser actions.
- Do not inspect evaluator files, backend code must not depend on private
  scenarios, and do not hard-code scenario answers.
- Keep the frontend minimal but usable. Prioritize selectors, state probe,
  routing, persistence, tables, uploads, services, and role/session behavior
  over decorative styling.

Behavior requirements inherited from the static-client benchmark prompt:
{requirements}

Requested visual variant:
{variant}

Public DSL contract:
```yaml
{contract}
```

{public_scenarios}

Return only JSON matching this shape:
{{
  "files": [
    {{"path": "package.json", "content": "..."}},
    {{"path": "server.js", "content": "..."}},
    {{"path": "public/index.html", "content": "..."}},
    {{"path": "public/styles.css", "content": "..."}},
    {{"path": "public/app.js", "content": "..."}}
  ],
  "notes": "short implementation summary"
}}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a blind backend-backed app from a DetoxBench DSL contract.")
    parser.add_argument("--contract-dsl", type=Path, required=True)
    parser.add_argument(
        "--public-scenarios-dsl",
        type=Path,
        action="append",
        help="Optional public scenario DSL file to include in the blind prompt.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--provider", choices=["openai", "anthropic", "google"], default="openai")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--base-url", help="Optional provider API base URL.")
    parser.add_argument("--max-output-tokens", type=int, default=48000)
    parser.add_argument("--request-timeout", type=int, default=600)
    parser.add_argument("--member-id", help="Optional model cohort member id recorded in generation metadata.")
    parser.add_argument(
        "--metadata-output",
        type=Path,
        help="Optional path for generation metadata JSON. Defaults to <output-dir>/generation.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contract_text = args.contract_dsl.read_text(encoding="utf-8")
    public_scenarios_text = static_gen.public_scenarios_section(args.public_scenarios_dsl or [])
    prompt = PROMPT.format(
        requirements=behavior_requirements(),
        variant=args.variant,
        contract=contract_text,
        public_scenarios=public_scenarios_text,
    )
    prompt_sha = sha256(prompt.encode("utf-8")).hexdigest()
    contract_sha = sha256(contract_text.encode("utf-8")).hexdigest()

    payload, response_metadata = generate_payload(
        provider=args.provider,
        model=args.model,
        prompt=prompt,
        max_output_tokens=args.max_output_tokens,
        base_url=args.base_url,
        request_timeout=args.request_timeout,
    )

    files = payload.get("files")
    if not isinstance(files, list):
        raise SystemExit("Model response did not include a files array")
    received = {str(item.get("path")) for item in files if isinstance(item, dict)}
    if received != EXPECTED_FILES:
        raise SystemExit(f"Model returned unexpected file set: {sorted(received)}")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for item in files:
        destination = output_dir / str(item["path"])
        if destination.resolve().is_relative_to(output_dir.resolve()) is False:
            raise SystemExit(f"Refusing to write outside output dir: {item['path']}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(str(item["content"]), encoding="utf-8")

    notes = str(payload.get("notes", ""))
    (output_dir / "GENERATION.md").write_text(
        "# Blind Backend-Backed DSL Generation\n\n"
        f"Provider: `{args.provider}`\n\n"
        f"Model: `{args.model}`\n\n"
        f"Cohort member: `{args.member_id or 'ad-hoc'}`\n\n"
        f"Contract SHA-256: `{contract_sha}`\n\n"
        f"Prompt SHA-256: `{prompt_sha}`\n\n"
        f"Variant: {args.variant}\n\n"
        f"{notes}\n",
        encoding="utf-8",
    )
    metadata = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generator": "tools/generate_blind_dsl_backend_app.py",
        "substrate": "express_json_file_storage",
        "member_id": args.member_id,
        "provider": args.provider,
        "model": args.model,
        "base_url": static_gen.redacted_base_url(args.base_url),
        "max_output_tokens": args.max_output_tokens,
        "request_timeout": args.request_timeout,
        "variant": args.variant,
        "contract_path": str(args.contract_dsl.resolve()),
        "public_scenarios_paths": [str(path.resolve()) for path in (args.public_scenarios_dsl or [])],
        "contract_sha256": contract_sha,
        "prompt_sha256": prompt_sha,
        "output_dir": str(output_dir.resolve()),
        "response": response_metadata,
        "git_commit": current_git_commit(),
        "files": sorted(received),
        "notes": notes,
    }
    metadata_path = args.metadata_output or output_dir / "generation.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "written": sorted(received),
                "metadata": str(metadata_path),
                "notes": notes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def generate_payload(
    *,
    provider: str,
    model: str,
    prompt: str,
    max_output_tokens: int,
    base_url: str | None,
    request_timeout: int,
) -> tuple[dict, dict]:
    if provider == "openai":
        return generate_openai_payload(model, prompt, max_output_tokens, base_url, request_timeout)
    if provider == "anthropic":
        return generate_anthropic_payload(model, prompt, max_output_tokens, base_url, request_timeout)
    if provider == "google":
        return generate_google_payload(model, prompt, max_output_tokens, request_timeout)
    raise SystemExit(f"Unsupported provider: {provider}")


def generate_openai_payload(
    model: str,
    prompt: str,
    max_output_tokens: int,
    base_url: str | None,
    request_timeout: int,
) -> tuple[dict, dict]:
    from openai import OpenAI

    client_kwargs = {"api_key": os.environ.get("OPENAI_API_KEY"), "timeout": request_timeout, "max_retries": 0}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    response = client.responses.create(
        model=model,
        input=prompt,
        max_output_tokens=max_output_tokens,
        text={
            "format": {
                "type": "json_schema",
                "name": "backend_app",
                "strict": True,
                "schema": response_schema(),
            }
        },
    )
    return json.loads(static_gen.extract_json_payload(response.output_text)), {"id": getattr(response, "id", None)}


def generate_anthropic_payload(
    model: str,
    prompt: str,
    max_output_tokens: int,
    base_url: str | None,
    request_timeout: int,
) -> tuple[dict, dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    api_base = (base_url or "https://api.anthropic.com").rstrip("/")
    response = static_gen.post_json(
        f"{api_base}/v1/messages",
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        body={
            "model": model,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        redacted_url=f"{api_base}/v1/messages",
        timeout=request_timeout,
    )
    text = "\n".join(
        block.get("text", "")
        for block in response.get("content", [])
        if block.get("type") == "text"
    )
    return json.loads(static_gen.extract_json_payload(text)), {
        "id": response.get("id"),
        "stop_reason": response.get("stop_reason"),
    }


def generate_google_payload(
    model: str,
    prompt: str,
    max_output_tokens: int,
    request_timeout: int,
) -> tuple[dict, dict]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set")
    model_path = model if model.startswith("models/") else f"models/{model}"
    model_path = "/".join(urllib.parse.quote(part, safe="") for part in model_path.split("/"))
    base = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:generateContent"
    response = static_gen.post_json(
        f"{base}?key={urllib.parse.quote(api_key, safe='')}",
        headers={"content-type": "application/json"},
        body={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": max_output_tokens,
            },
        },
        redacted_url=f"{base}?key=***",
        timeout=request_timeout,
    )
    candidates = response.get("candidates") or []
    if not candidates:
        raise SystemExit(f"Google response did not include candidates: {response!r}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts)
    return json.loads(static_gen.extract_json_payload(text)), {
        "model": response.get("modelVersion") or response.get("model"),
        "finish_reason": candidates[0].get("finishReason"),
    }


def response_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "files": {
                "type": "array",
                "minItems": 5,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string", "enum": sorted(EXPECTED_FILES)},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["files", "notes"],
    }


def current_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
