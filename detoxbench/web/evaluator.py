from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urlparse
from urllib.parse import urljoin

from playwright.sync_api import BrowserContext, Page, Route, sync_playwright

from detoxbench.core.assertions import evaluate_assertions
from detoxbench.core.logging import JsonlRunLogger
from detoxbench.core.models import (
    Contract,
    RunResult,
    ScenarioResult,
    ScenarioSet,
    StepResult,
)
from detoxbench.web.local_server import StaticServer


@dataclass(frozen=True)
class WebEvaluationConfig:
    app_url: str | None
    static_dir: Path | None
    output_dir: Path
    run_subject: str = "unknown"
    headless: bool = True
    slow_mo_ms: int = 0
    action_timeout_ms: int = 5000
    screenshot_policy: str = "all"


class WebEvaluator:
    def __init__(
        self,
        contract: Contract,
        scenarios: ScenarioSet,
        config: WebEvaluationConfig,
    ) -> None:
        self.contract = contract
        self.scenarios = scenarios
        self.config = config
        if self.config.screenshot_policy not in {"all", "failures", "none"}:
            raise ValueError("screenshot_policy must be all, failures, or none")
        self.run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.run_dir = self.config.output_dir / self.run_id
        self.screenshot_dir = self.run_dir / "screenshots"
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.service_calls: list[dict[str, Any]] = []

    def run(self) -> RunResult:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        server = None
        app_url = self.config.app_url
        if not app_url:
            if not self.config.static_dir:
                raise ValueError("Either app_url or static_dir must be configured")
            server = StaticServer(self.config.static_dir).start()
            app_url = urljoin(server.url + "/", self.contract.start_path.lstrip("/"))

        try:
            result = self._run_browser(app_url)
        finally:
            if server:
                server.stop()

        summary_path = self.run_dir / "summary.json"
        summary_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result

    def _run_browser(self, app_url: str) -> RunResult:
        scenario_results: list[ScenarioResult] = []
        log_path = self.run_dir / "events.jsonl"

        with JsonlRunLogger(log_path) as logger:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=self.config.headless,
                    slow_mo=self.config.slow_mo_ms,
                )
                try:
                    for scenario in self.scenarios.scenarios:
                        context = browser.new_context(viewport={"width": 1280, "height": 900})
                        self.service_calls = []
                        self._install_service_routes(context)
                        pages = self._open_scenario_pages(context, app_url, scenario)
                        try:
                            result = self._run_scenario(pages, scenario, logger)
                            scenario_results.append(result)
                        finally:
                            for page in pages.values():
                                page.close()
                            context.close()
                finally:
                    browser.close()

        return RunResult(
            run_id=self.run_id,
            subject=self.config.run_subject,
            output_dir=str(self.run_dir),
            scenarios=scenario_results,
        )

    def _open_scenario_pages(
        self,
        context: BrowserContext,
        app_url: str,
        scenario: dict[str, Any],
    ) -> dict[str, Page]:
        actors = _scenario_actors(scenario)
        if not actors:
            actors = ["__default__"]

        pages: dict[str, Page] = {}
        for actor in actors:
            page = context.new_page()
            page.set_default_timeout(self.config.action_timeout_ms)
            page.set_default_navigation_timeout(self.config.action_timeout_ms)
            page.goto(self._actor_start_url(app_url, actor), wait_until="networkidle")
            pages[actor] = page
        return pages

    def _actor_start_url(self, app_url: str, actor: str) -> str:
        if actor == "__default__":
            return app_url
        web_runtime = self.contract.runtime.get("web", {})
        actors = web_runtime.get("actors", {})
        if not isinstance(actors, dict):
            return app_url
        actor_config = actors.get(actor, {})
        if not isinstance(actor_config, dict):
            return app_url
        start_path = actor_config.get("start_path")
        if isinstance(start_path, str) and start_path.startswith("/"):
            return _same_origin_url(app_url, start_path)
        start_page = actor_config.get("start_page")
        pages = web_runtime.get("pages", {})
        if isinstance(start_page, str) and isinstance(pages, dict):
            path = _runtime_page_path(pages.get(start_page))
            if path:
                return _same_origin_url(app_url, path)
        return app_url

    def _run_scenario(
        self,
        pages: dict[str, Page],
        scenario: dict[str, Any],
        logger: JsonlRunLogger,
    ) -> ScenarioResult:
        scenario_id = str(scenario["id"])
        self.snapshots = {}
        steps: list[StepResult] = []
        passed = True
        error: str | None = None
        error_step_index: int | None = None
        current_step_index: int | None = None
        expected_step_count = len(scenario.get("steps", []))

        try:
            for index, step in enumerate(scenario["steps"], start=1):
                current_step_index = index
                result = self._run_step(pages, scenario_id, index, step)
                steps.append(result)
                logger.write(
                    {
                        "run_id": self.run_id,
                        "event": "step",
                        **result.to_dict(),
                    }
                )
                if not result.passed:
                    passed = False
        except Exception as exc:  # noqa: BLE001 - benchmark errors belong in artifacts.
            passed = False
            error = f"{exc.__class__.__name__}: {exc}"
            error_step_index = current_step_index or len(steps) + 1
            logger.write(
                {
                    "run_id": self.run_id,
                    "event": "scenario_error",
                    "scenario_id": scenario_id,
                    "step_index": error_step_index,
                    "error": error,
                }
            )

        scenario_result = ScenarioResult(
            id=scenario_id,
            passed=passed,
            steps=steps,
            error=error,
            tier=scenario.get("tier"),
            kind=str(scenario.get("kind", "scoring")),
            weight=float(scenario.get("weight", 1.0)),
            visibility=str(scenario.get("visibility", "private")),
            difficulty=scenario.get("difficulty"),
            contract_refs=list(scenario.get("contract_refs", [])),
            description=scenario.get("description"),
            expected_step_count=expected_step_count,
            error_step_index=error_step_index,
            source=scenario.get("_source"),
        )
        logger.write(
            {
                "run_id": self.run_id,
                "event": "scenario_complete",
                **scenario_result.to_dict(),
            }
        )
        return scenario_result

    def _run_step(
        self,
        pages: dict[str, Page],
        scenario_id: str,
        index: int,
        step: dict[str, Any],
    ) -> StepResult:
        action = str(step.get("action", "snapshot"))
        component_id = step.get("component")
        actor = str(step.get("actor")) if step.get("actor") else None
        page = self._page_for_step(pages, actor)

        before_state = self._capture_state(page)
        self.snapshots["before"] = before_state
        before_screenshot = None
        if self.config.screenshot_policy != "none":
            before_screenshot = self._screenshot(page, scenario_id, index, "before")

        if action != "snapshot":
            self._perform_action(page, action, step)
            page.wait_for_timeout(int(step.get("settle_ms", 50)))

        after_state = self._capture_state(page)
        self.snapshots["after"] = after_state
        after_screenshot = None
        if self.config.screenshot_policy != "none":
            after_screenshot = self._screenshot(page, scenario_id, index, "after")

        save_as = step.get("save_as") or step.get("as")
        if save_as:
            self.snapshots[str(save_as)] = after_state

        assertions = evaluate_assertions(
            list(step.get("expect", [])),
            after_state=after_state,
            snapshots=self.snapshots,
        )

        if self.config.screenshot_policy == "failures" and all(
            assertion.passed for assertion in assertions
        ):
            for screenshot in (before_screenshot, after_screenshot):
                if screenshot is not None:
                    screenshot.unlink(missing_ok=True)
            before_screenshot = None
            after_screenshot = None

        return StepResult(
            scenario_id=scenario_id,
            step_index=index,
            action=action,
            component=str(component_id) if component_id else None,
            before_state=before_state,
            after_state=after_state,
            before_screenshot=str(before_screenshot) if before_screenshot else None,
            after_screenshot=str(after_screenshot) if after_screenshot else None,
            assertions=assertions,
            actor=actor,
        )

    def _page_for_step(self, pages: dict[str, Page], actor: str | None) -> Page:
        key = actor or "__default__"
        try:
            return pages[key]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario actor page: {key}") from exc

    def _install_service_routes(self, context: BrowserContext) -> None:
        services = self.contract.runtime.get("web", {}).get("services", {})
        if not isinstance(services, dict) or not services:
            return
        for service_id, raw_service in services.items():
            if not isinstance(raw_service, dict):
                continue
            endpoint = raw_service.get("endpoint")
            if not isinstance(endpoint, str) or not endpoint.startswith("/"):
                continue
            context.route(
                f"**{endpoint}**",
                lambda route, _request=None, service_id=str(service_id), service=raw_service: self._fulfill_service_route(
                    route,
                    service_id,
                    service,
                ),
            )

    def _fulfill_service_route(self, route: Route, service_id: str, service: dict[str, Any]) -> None:
        request = route.request
        parsed = urlparse(request.url)
        query = {
            key: values[-1] if values else ""
            for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
        }
        body_json: dict[str, Any] = {}
        post_data = request.post_data
        if post_data:
            try:
                parsed_body = json.loads(post_data)
                if isinstance(parsed_body, dict):
                    body_json = parsed_body
            except json.JSONDecodeError:
                body_json = {}

        response = _select_service_response(service, method=request.method, query=query, body_json=body_json)
        call = {
            "service": service_id,
            "method": request.method,
            "path": parsed.path,
            "query": query,
            "body_json": body_json,
            "response_id": response.get("id"),
            "status": response.get("status", 200),
        }
        self.service_calls.append(call)
        headers = {"access-control-allow-origin": "*"}
        if "json" in response:
            route.fulfill(
                status=int(response.get("status", 200)),
                headers={**headers, "content-type": "application/json"},
                body=json.dumps(response["json"], ensure_ascii=False),
            )
            return
        route.fulfill(
            status=int(response.get("status", 200)),
            headers={**headers, "content-type": "text/plain"},
            body=str(response.get("text", "")),
        )

    def _perform_action(self, page: Page, action: str, step: dict[str, Any]) -> None:
        if action == "wait":
            page.wait_for_timeout(int(step.get("ms", 100)))
            return
        if action == "reload":
            page.reload(wait_until="networkidle")
            return
        if action == "back":
            page.go_back(wait_until="networkidle")
            return
        if action == "forward":
            page.go_forward(wait_until="networkidle")
            return
        if action == "goto":
            path = step.get("path")
            if not isinstance(path, str) or not path.startswith("/"):
                raise ValueError("Action 'goto' requires a browser path starting with '/'")
            page.goto(_same_origin_url(page.url, path), wait_until="networkidle")
            return
        if action == "event":
            event_id = step.get("event")
            if not isinstance(event_id, str) or not event_id:
                raise ValueError("Action 'event' requires event id")
            payload = step.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            page.evaluate(
                """({eventId, payload}) => {
                    window.dispatchEvent(new CustomEvent("detoxbench:event", {
                        detail: { id: eventId, payload }
                    }));
                }""",
                {"eventId": event_id, "payload": payload},
            )
            return

        component_id = step.get("component")
        if not component_id:
            raise ValueError(f"Action {action!r} requires component")
        component = self.contract.components.get(str(component_id))
        if not component:
            raise KeyError(f"Unknown component: {component_id}")
        if action not in component.actions:
            raise ValueError(f"Action {action!r} is not declared for component {component_id!r}")

        selector = str(step.get("selector") or component.selector)
        locator = page.locator(selector)
        if "index" in step:
            locator = locator.nth(int(step["index"]))

        if action == "click":
            locator.click()
            return
        if action == "fill":
            locator.fill(str(step.get("value", "")))
            return
        if action == "upload":
            file_payload = step.get("file")
            if not isinstance(file_payload, dict):
                raise ValueError("Action 'upload' requires file payload")
            name = file_payload.get("name")
            content = file_payload.get("content")
            if not isinstance(name, str) or not name:
                raise ValueError("Action 'upload' requires file.name")
            if not isinstance(content, str):
                raise ValueError("Action 'upload' requires string file.content")
            mime_type = file_payload.get("mime_type")
            if not isinstance(mime_type, str) or not mime_type:
                mime_type = "text/plain"
            locator.set_input_files(
                {
                    "name": name,
                    "mimeType": mime_type,
                    "buffer": content.encode("utf-8"),
                }
            )
            return
        if action == "press":
            locator.press(str(step["key"]))
            return
        if action == "check":
            locator.check()
            return
        if action == "uncheck":
            locator.uncheck()
            return
        if action == "select":
            locator.select_option(str(step["value"]))
            return
        if action == "hover":
            locator.hover()
            return
        if action == "focus":
            locator.focus()
            return

        raise ValueError(f"Unsupported action: {action}")

    def _capture_state(self, page: Page) -> dict[str, Any]:
        state = page.evaluate(self.contract.state_expression)
        if not isinstance(state, dict):
            raise TypeError("state_expression must return an object/dict")
        state = dict(state)
        state["__browser"] = self._capture_browser_state(page)
        state["__services"] = {"calls": list(self.service_calls)}
        state["__tables"] = self._capture_table_state(page)
        return state

    def _capture_table_state(self, page: Page) -> dict[str, Any]:
        tables = self.contract.runtime.get("web", {}).get("tables", {})
        if not isinstance(tables, dict) or not tables:
            return {}
        return page.evaluate(
            """(tables) => {
                const result = {};
                for (const [tableId, table] of Object.entries(tables)) {
                    const root = document.querySelector(table.selector);
                    const rowSelector = table.row_selector;
                    const rowIdAttribute = table.row_id_attribute || "data-row-id";
                    const columns = table.columns || {};
                    const captured = { missing: !root, order: [], rows: {}, count: 0 };
                    if (!root || !rowSelector) {
                        result[tableId] = captured;
                        continue;
                    }
                    const rows = Array.from(root.querySelectorAll(rowSelector));
                    for (const row of rows) {
                        const rowId = row.getAttribute(rowIdAttribute);
                        if (!rowId) {
                            continue;
                        }
                        captured.order.push(rowId);
                        const cells = {};
                        for (const [columnId, column] of Object.entries(columns)) {
                            const selector = typeof column === "string" ? column : column.selector;
                            const cell = selector ? row.querySelector(selector) : null;
                            cells[columnId] = cell ? cell.textContent.trim() : "";
                        }
                        captured.rows[rowId] = cells;
                    }
                    captured.count = captured.order.length;
                    result[tableId] = captured;
                }
                return result;
            }""",
            tables,
        )

    def _capture_browser_state(self, page: Page) -> dict[str, Any]:
        location = page.evaluate(
            "() => ({"
            "url: window.location.href,"
            "pathname: window.location.pathname,"
            "search: window.location.search,"
            "hash: window.location.hash"
            "})"
        )
        if not isinstance(location, dict):
            raise TypeError("browser location probe must return an object/dict")
        path = f"{location.get('pathname', '')}{location.get('search', '')}{location.get('hash', '')}"
        return {
            "url": location.get("url"),
            "path": path,
            "page_id": self._resolve_page_id(path),
        }

    def _resolve_page_id(self, path: str) -> str | None:
        pages = self.contract.runtime.get("web", {}).get("pages", {})
        if not isinstance(pages, dict):
            return None
        for page_id, page in pages.items():
            expected = page.get("path") if isinstance(page, dict) else page
            if not isinstance(expected, str):
                continue
            if _browser_path(expected) == path:
                return str(page_id)
        return None

    def _screenshot(
        self,
        page: Page,
        scenario_id: str,
        index: int,
        phase: str,
    ) -> Path:
        safe_scenario = _safe_path_part(scenario_id)
        path = self.screenshot_dir / safe_scenario / f"{index:03d}-{phase}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=True)
        return path


def _safe_path_part(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)


def _scenario_actors(scenario: dict[str, Any]) -> list[str]:
    actors: list[str] = []
    for step in scenario.get("steps", []):
        if not isinstance(step, dict):
            continue
        actor = step.get("actor")
        if isinstance(actor, str) and actor and actor not in actors:
            actors.append(actor)
    return actors


def _runtime_page_path(page: Any) -> str | None:
    if isinstance(page, str) and page.startswith("/"):
        return page
    if isinstance(page, dict):
        path = page.get("path")
        if isinstance(path, str) and path.startswith("/"):
            return path
    return None


def _browser_path(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return f"{parsed.path}{('?' + parsed.query) if parsed.query else ''}{('#' + parsed.fragment) if parsed.fragment else ''}"
    return value


def _same_origin_url(current_url: str, path: str) -> str:
    parsed = urlparse(current_url)
    if not parsed.scheme or not parsed.netloc:
        return path
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _select_service_response(
    service: dict[str, Any],
    *,
    method: str,
    query: dict[str, Any],
    body_json: dict[str, Any],
) -> dict[str, Any]:
    expected_method = str(service.get("method", "GET")).upper()
    if method.upper() != expected_method:
        return {
            "id": "method_not_allowed",
            "status": 405,
            "json": {"error": "method_not_allowed"},
        }

    for response in service.get("responses", []):
        if not isinstance(response, dict):
            continue
        match = response.get("match", {})
        if not isinstance(match, dict):
            match = {}
        if _mapping_matches(query, match.get("query", {})) and _mapping_matches(
            body_json,
            match.get("body_json", {}),
        ):
            return response

    return {
        "id": "not_found",
        "status": int(service.get("default_status", 404)),
        "json": {"error": "not_found"},
    }


def _mapping_matches(actual: dict[str, Any], expected: Any) -> bool:
    if expected in (None, {}):
        return True
    if not isinstance(expected, dict):
        return False
    for key, expected_value in expected.items():
        if key not in actual:
            return False
        actual_value = actual[key]
        if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
            try:
                actual_value = float(actual_value)
            except (TypeError, ValueError):
                return False
        if actual_value != expected_value:
            return False
    return True
