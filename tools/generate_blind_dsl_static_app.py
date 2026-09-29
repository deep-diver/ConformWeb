from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request


PROMPT = """You are generating a blind DetoxBench candidate web app from a public DSL contract only.

Do not assume access to hidden evaluator scenarios. Implement the public behavior
declared by the contract and any public scenario examples included below, not a
guessed hidden test script.

Create a runnable static web app with exactly these files:
- index.html
- styles.css
- app.js

Requirements:
- Implement every component selector from the DSL contract exactly.
- The element matched by each selector must be directly actionable by browser
  automation; do not put the selector on a hidden input or an element covered by
  a decorative proxy.
- Implement every declared component action.
- Expose public app state through the exact state probe expression declared in
  runtime.state_probe.expression.
- The state object must contain every path declared in state.schema.
- If state.initial is present, initialize the app state to those exact values.
- Follow action preconditions and effects from the public contract.
- For DSL v0.3 blocked semantics, implement blocked_when / blocked_effects as
  deliberate no-op attempts. Components with blocked behavior must remain
  directly actionable by browser automation in the blocked state; do not rely on
  a disabled HTML control to satisfy blocked behavior.
- For DSL v0.4 equals_template effects, render the declared state template from
  the current public state after the action. Tokens like {{value}} read a state
  path, {{history.length}} reads the length of an array/string state path, and
  {{last_action|default:none}} uses the default when the state value is empty or
  null.
- For DSL v0.4.1 equals_linear effects, compute the declared numeric path from
  after-state public values: start with optional constant, add each term's
  state path multiplied by its optional multiplier, then apply optional round.
- For DSL v0.4.2 equals_piecewise_linear effects, evaluate cases in order
  against after-state public values. Use the first case whose when conditions
  are all true, then compute that case's formula like equals_linear. If no case
  matches, compute the default formula. Empty terms with a constant are valid in
  piecewise formulas.
- For DSL v0.5.0 collection effects, treat arrays as ordered public state:
  removed_first removes only the first item, equals_length derives a number from
  an array/string length, equals_count_where counts array items matching all
  declared item-field conditions, equals_sum sums a numeric field across
  matching array items, equals_any_where derives a boolean from whether any item
  matches, and equals_first_item_field / equals_last_item_field project a field
  from the first or last item or use the declared default when the array is
  empty.
- For DSL v0.6.0 collection identity effects, use item-field predicates against
  ordered public arrays: removed_first_where removes the first matching item,
  updated_first_where shallow-merges the declared updates into the first
  matching object item, moved_first_where moves the first matching item to the
  declared zero-based index, and appended_from_first_where appends the first
  matching item from another before-state source array to the destination array,
  shallow-merging declared updates when present. If an action also declares a
  remove effect on the source array, apply both effects as one action.
- For DSL v0.7.0 dynamic collection creation, appended_object appends a new
  public object to the end of an ordered public array. Render each declared
  value field from the public state: from_path reads the before-action state,
  after_path reads the after-action state, and literal values stay literal.
- For DSL v0.8.0 view projection effects, equals_filter means the destination
  public array must equal the source_path public array after applying all item
  where predicates and optional order_by fields in order. Filtering and sorting
  are public behavior, not evaluator-private logic.
- For DSL v0.9.0 validation and state-bound item identity, implement
  rejected_when / rejected_effects as deliberate rejected action attempts, like
  blocked attempts except the rejection may set declared error/status fields.
  Components with rejected behavior must remain directly actionable; do not use
  a disabled HTML control for rejected behavior. Item predicates may use
  value_path, which compares the item's public field to another current public
  state path such as selected_id.
- For DSL v1.1.0 multipage contracts, implement runtime.pages as real browser
  navigation, not only CSS tabs. A page path such as /#/review must be reflected
  in window.location after navigation. A component with page: <id> should be
  available and actionable on that page. An action with navigate_to: <id> must
  move the browser to the declared page path and update any declared public
  state effects.
- For DSL v1.2.0 async contracts, implement async_effects with real asynchronous
  behavior. The normal action effects describe the immediate post-action state,
  such as request_status: submitting. The async_effects.effects describe the
  later public state after async_effects.after_ms has elapsed. Use a timer or
  equivalent browser async mechanism, keep the state probe current throughout
  the lifecycle, and do not jump directly to the final state before the
  immediate pending state can be observed.
- For DSL v1.3.0 dynamic row contracts, implement selector_template components
  by rendering actual DOM elements whose selectors can be resolved from scenario
  input. For example, selector_template
  [data-row-id="{{input.ticket_id}}"] [data-testid="resolve-row"] requires each
  row to expose data-row-id equal to the public item id and to contain the
  declared row action button. Item where predicates may use value_from:
  input.<field>; treat that as the clicked row/input identity when updating the
  first matching public array item.
- For DSL v1.3.1 / v1.4.0 bulk collection contracts, updated_all_where and
  removed_all_where are true multi-item operations over ordered public arrays.
  updated_all_where must shallow-merge the declared updates into every object
  item matching all predicates, preserving non-matching items and order.
  removed_all_where must remove every matching item, preserving non-matching
  items and order. A partial bulk operation must not silently clear or mutate
  unrelated matching dimensions: for example, an operation that updates only
  selected high-risk rows must preserve selected standard-risk rows unless the
  public effects explicitly update them.
- For DSL v1.5.0 field validation contracts, object-valued public state such as
  field_errors is first-class behavior. updated_object_fields shallow-merges the
  declared field updates into the before-state object. removed_object_fields
  removes only the declared keys from the before-state object. Do not collapse a
  public error object into a single message string. Rejected validation actions
  must update exactly the declared error keys, field correction actions must
  remove exactly the declared error keys, and unrelated errors must be preserved.
  equals_object_key_count derives a number from the current key count of another
  public object.
- For DSL v1.6.0 nested collection contracts, parent arrays may contain child
  arrays. updated_first_child_where must find the first parent matching
  parent_where, then the first child under child_path matching child_where, and
  shallow-merge only that child with updates. removed_first_child_where removes
  only that first matching child from the matching parent. equals_nested_count_where
  and equals_nested_sum derive values across child arrays of matching parents.
  Preserve parent order, child order, sibling children, and unrelated parents.
- For DSL v1.7.0 logical-time contracts, advanced_time_by moves the declared
  public clock path by the declared amount. updated_all_where_after and
  removed_all_where_after transform the before-state array, but evaluate their
  where predicates against the after-action public state. This matters when the
  same action first advances a public clock and then promotes every item whose
  due_at is now <= that new clock. Do not use real wall-clock time for these
  transitions unless async_effects explicitly requires it.
- For DSL v2.0.0 role/session contracts, runtime.session declares a public
  role_path and the complete list of valid roles. Actions may declare
  allowed_roles. When the current public role_path value is in allowed_roles,
  the normal action effects apply. When it is not, the control must remain
  directly actionable and unauthorized_effects must apply instead. Do not hide
  denied behavior behind disabled controls, missing buttons, private auth state,
  or alerts that do not update the declared public state. Role changes are
  ordinary public state transitions declared by components in the contract.
- For DSL v2.0.1 reload-persistence contracts, runtime.persistence.reload
  declares public state paths that must survive a real browser reload. If the
  contract declares scope: local_storage, persist those paths through
  localStorage; if it declares scope: session_storage, persist through
  sessionStorage; if it declares scope: url, encode enough public state in the
  URL to restore those paths. Scenario tests may call browser reload without
  clicking a component, so in-memory JavaScript state alone is not sufficient.
  Reload must restore the declared public state paths and keep the state probe
  current after page load.
- For DSL v2.1.0 browser lifecycle contracts, scenario tests may navigate the
  browser directly with goto, back, and forward without clicking app controls.
  Implement runtime.pages as actual browser history entries. A direct visit to a
  declared page path must render that page and update the public route state.
  Browser back/forward must restore the route and preserve any declared
  persisted public state. Component navigation should use pushState or normal
  same-origin navigation when it is meant to create history; do not fake pages
  with private tabs while leaving window.location unchanged.
- For DSL v2.2.0 multi-actor contracts, runtime.actors declares named actors
  that the evaluator may drive in separate browser pages within one scenario.
  Each actor starts at its declared start_page or start_path. Scenario actions
  may be performed by different actors without resetting the app. Shared public
  workflow state must be observable across actor pages after declared sync
  points such as reload, route navigation, or storage events. Actor-specific
  browser history must remain real browser history for that actor page. Do not
  implement actor behavior as evaluator-private flags or hard-coded scenario
  scripts; it must follow the public contract and state probe.
- For DSL v2.3.0 deterministic service fixture contracts, runtime.services
  declares evaluator-provided same-origin HTTP endpoints. Implement real
  browser fetch/XHR calls to those endpoints when the public workflow requires
  a lookup, quote, validation, or adjudication. Do not replace service calls
  with a hard-coded table in private JavaScript. The evaluator records calls in
  __services.calls, so public counters such as service_call_count must stay
  aligned with real network requests. Match query/body fields exactly as the
  contract declares, consume the JSON/text response, and update public state
  from that response.
- For DSL v2.4.0 deterministic system event contracts, runtime.events declares
  evaluator-injected CustomEvent messages on window named detoxbench:event. The
  event detail contains {{ id, payload }}. Listen for that public event, match
  detail.id to the declared runtime event id, apply its preconditions/effects
  against exposed public state, and keep the state probe current. Do not require
  a user click, private timer, hidden scenario flag, or hard-coded scenario
  script for these transitions.
- For DSL v2.5.0 rendered table/grid contracts, runtime.tables declares real
  DOM tables or grids that the evaluator inspects separately from
  window.__DETOX_STATE__. Render every table selector, row selector,
  row_id_attribute, and column selector exactly. Row order in the DOM must match
  the public visible/projection state after each action. Cell text should expose
  the declared public cell values without hidden-only or CSS-only substitutes.
- For DSL v2.6.0 file-input contracts, upload actions are real browser file
  uploads. Render an actual input[type="file"] at the declared selector, parse
  uploaded file content according to the public component purpose/contract, and
  update public state from the file data. Do not fake upload by requiring a
  separate button or by hard-coding scenario rows; the evaluator calls
  set_input_files on the declared input and expects the app change handler to
  produce the declared public state.
- For DSL v2.7.0 normalization contracts, equals_normalized means the contract
  has intentionally declared the comparison rule. Implement normalized public
  fields so they compare correctly under the listed normalizers: trim,
  collapse_whitespace, lowercase, uppercase, digits_only, and currency_number.
  Do not invent hidden normalization rules for fields that do not declare them.
- For DSL v2.8.0 conflict contracts, an action may have both normal
  preconditions/effects and conflict_when/conflict_effects. Implement the
  action as one user control whose behavior branches from public state at click
  time. When conflict_when is true, apply only conflict_effects; do not also
  apply the normal effects, mutate hidden rollback state, or consume inventory
  just because the user clicked the same button.
- For DSL v2.9.0 joined projection contracts, equals_join_projection means a
  public array must be derived from a source collection joined to a lookup
  collection by the declared keys. Preserve source order after filtering, copy
  only the declared output fields, and keep the rendered UI synchronized with
  that public projection.
- For DSL v3.0.0 typed upload contracts, upload actions may declare
  file_schema.format=csv with column names and types. Use that public schema
  when parsing uploaded files: number columns become JavaScript numbers,
  boolean columns become booleans, and string columns remain strings.
- Interpret DSL effect operations by their public transition semantics:
  - equals: after-state path equals the declared value.
  - changed_by: after-state numeric path equals before-state plus by.
  - advanced_time_by: after-state numeric clock path equals before-state plus
    by; this is deterministic logical time, not Date.now().
  - changed_by_path: after-state numeric path equals before-state path plus the
    before-state by_path times optional multiplier.
  - appended: after-state array path equals before-state array plus the declared
    item appended at the end, preserving order.
  - length_changed_by: after-state string/array length changes by by.
  - contains / not_contains: after-state string/array includes or excludes the
    declared item.
  - matches: after-state string matches the declared regular expression.
  - equals_template: after-state string equals the declared state template
    rendered from the after-state.
  - equals_linear: after-state number equals the declared linear formula
    rendered from after-state number paths.
  - equals_piecewise_linear: after-state number equals the first matching
    declared conditional linear formula evaluated against after-state public
    values.
  - removed_first: after-state array equals the before-state array without its
    first item.
  - equals_length: after-state number equals the length of source_path.
  - equals_count_where: after-state number equals the number of source_path
    array items whose public item fields match all declared where conditions.
  - equals_sum: after-state number equals the sum of a numeric item field across
    source_path array items matching all declared where conditions, plus any
    constant and multiplier.
  - equals_any_where: after-state boolean equals whether any source_path array
    item matches all declared where conditions.
  - equals_first_item_field / equals_last_item_field: after-state scalar equals
    the declared field from the first/last source_path array item, or the
    declared default when empty.
  - removed_first_where: after-state array equals the before-state array without
    the first item whose public fields match all declared where conditions.
  - updated_first_where: after-state array equals the before-state array with
    the first matching object item shallow-merged with the declared updates.
  - updated_all_where: after-state array equals the before-state array with
    every matching object item shallow-merged with the declared updates.
  - updated_all_where_after: after-state array equals the before-state array
    with every object item matching all where predicates against after-state
    public values shallow-merged with updates.
  - moved_first_where: after-state array equals the before-state array with the
    first matching item moved to the declared zero-based to_index.
  - removed_all_where: after-state array equals the before-state array with
    every item matching all declared where conditions removed.
  - removed_all_where_after: after-state array equals the before-state array
    with every item matching all where predicates against after-state public
    values removed.
  - updated_object_fields: after-state object equals the before-state object
    shallow-merged with the declared updates.
  - removed_object_fields: after-state object equals the before-state object
    with only the declared keys removed.
  - equals_object_key_count: after-state number equals the number of own keys in
    the declared source_path object.
  - updated_first_child_where: after-state parent array equals the before-state
    parent array with the first matching child under the first matching parent
    shallow-merged with updates.
  - removed_first_child_where: after-state parent array equals the before-state
    parent array with the first matching child under the first matching parent
    removed.
  - equals_nested_count_where: after-state number equals the count of nested
    child items matching child_where under parents matching parent_where.
  - equals_nested_sum: after-state number equals the sum of a numeric child
    field across nested child items matching child_where under parents matching
    parent_where, plus any declared constant and multiplier.
  - appended_from_first_where: after-state destination array equals the
    before-state destination array with the first matching item from the
    before-state source_path appended, shallow-merged with updates when present.
  - appended_object: after-state array equals the before-state array plus a new
    object rendered from the declared value template appended at the end.
  - equals_filter: after-state destination array equals the source_path array
    filtered by declared item predicates and sorted by optional order_by rules.
  - item where value_from: compare the item field to the scenario-provided
    input value that also resolves selector_template row identity.
  - changed / unchanged: after-state path differs from or equals before-state.
  - toggled: after-state boolean path is the inverse of before-state.
  - relation: after-state path satisfies the declared operator against a literal
    value or another public state path.
  - truthy / falsey: after-state path has the corresponding boolean coercion.
  - one_of / not_one_of: after-state path is included in or excluded from the
    declared values list.
  - unauthorized_effects: when the current runtime.session role_path value is
    not in action.allowed_roles, after-state must satisfy the declared
    unauthorized effects instead of the normal effects.
- Async semantics:
  - action.effects are checked immediately after the action.
  - action.async_effects.after_ms declares when delayed public effects should
    be observable.
  - action.async_effects.effects are delayed effects, not private scenario
    answers.
- Dynamic row semantics:
  - selector_template is a public selector contract, not a hint.
  - Render row identifiers into the DOM so browser automation can click the
    specific row action.
  - Row actions must update the matching public array item, not whichever row
    happens to be first or currently highlighted.
- Bulk row semantics:
  - Bulk controls must operate over all public items matching the declared where
    predicates.
  - Preserve item order after bulk updates.
  - Preserve non-matching rows exactly unless a separate public effect changes
    them.
- Field validation semantics:
  - Public validation state should be represented with the declared object paths.
  - Clearing a field error must not clear unrelated field errors unless the
    public effect lists those keys.
  - Error counters and badges should derive from the actual public error object,
    not from hidden UI-only bookkeeping.
- Nested collection semantics:
  - Treat child arrays as part of the public parent object state.
  - A parent predicate scopes where child matching occurs.
  - A child operation must not flatten all children and then lose the parent
    relationship when writing the updated state back.
  - Derived nested counts and sums should be recomputed from actual public child
    arrays after every action.
- Logical-time semantics:
  - Public clock fields are ordinary public state fields and must be exposed in
    window.__DETOX_STATE__.
  - Scheduled updates should be driven by the declared public clock after the
    action, not by private timers or the user's local clock.
  - Preserve non-matching scheduled rows exactly, including completed rows that
    are not yet expired.
- Role/session semantics:
  - runtime.session.role_path is a normal public state path and must be exposed
    through the state probe.
  - allowed_roles is not a UI hint; it is the public permission rule for the
    action.
  - Unauthorized actions should be clickable and should update only the public
    state declared by unauthorized_effects.
  - A candidate that merely disables or removes disallowed controls fails the
    UI contract because the evaluator must be able to perform the denied action.
- Multipage semantics:
  - runtime.pages declares public page ids and browser paths.
  - component.page declares where that component is expected to be used.
  - action.navigate_to declares the page reached after the action.
  Use hash routing or normal same-origin links; either is fine as long as
  browser location matches the declared path.
- Browser lifecycle semantics:
  - browser reload, goto, back, and forward are evaluator actions, not
    component clicks.
  - Direct deep links should initialize the route from window.location.
  - popstate/hashchange handling must keep window.__DETOX_STATE__ synchronized
    with the browser path.
- Multi-actor semantics:
  - runtime.actors is a public contract for multiple driven browser pages.
  - Each actor page should initialize from its declared start route.
  - Cross-actor handoffs should use declared public shared state and declared
    persistence/synchronization, not private evaluator knowledge.
  - Actor route history is per actor page; one actor going back/forward must not
    silently move another actor's browser location.
- Service fixture semantics:
  - runtime.services endpoint paths are real HTTP contracts.
  - Fetch the declared endpoint with the declared method and query/body shape.
  - Apply response JSON/text to public app state through ordinary state updates.
  - Keep declared service counters and trace-derived public state in sync with
    actual network calls observed by the evaluator.
- System event semantics:
  - runtime.events ids are public event contracts.
  - React to window CustomEvent("detoxbench:event") with detail.id and
    detail.payload.
  - Event payload values are public input data for the event, not private test
    answers.
  - Event effects should be applied exactly once per dispatched event and
    persisted when runtime.persistence declares those state paths.
- Rendered table/grid semantics:
  - runtime.tables selectors are part of the UI contract, not styling hints.
  - Each rendered row must expose the declared row_id_attribute with the public
    row id.
  - Each declared column selector must resolve inside the corresponding row.
  - Table order, row count, and cell text must stay synchronized with public
    state projections such as visible_flights, visible_orders, or filtered rows.
- File input semantics:
  - upload actions require a visible, enabled file input at the declared
    selector.
  - Use the browser File API and change events to read uploaded content.
  - CSV-like inputs should be parsed into typed public rows when the contract
    declares numeric or boolean fields.
  - Replacement uploads replace the public batch when the contract effects say
    equals value_from input.rows rather than append.
- Normalization semantics:
  - trim removes leading/trailing whitespace.
  - collapse_whitespace converts any run of whitespace to one space.
  - lowercase and uppercase change case after earlier normalizers in order.
  - digits_only removes every non-digit character.
  - currency_number removes currency/grouping text and compares the numeric
    string without unnecessary trailing zeroes.
- Conflict semantics:
  - A conflict mode is not a separate hidden test hook. It is the observable
    result of clicking the same public component while conflict_when is true.
  - Conflict effects replace normal effects for that click.
  - Unchanged conflict paths must remain bit-for-bit equal to the before-click
    public state, while conflict status/error fields may update when declared.
- Joined projection semantics:
  - source_path and lookup_path are public state arrays.
  - Join each source item to one lookup item using source_key and lookup_key.
  - Apply where filters to source items before projection.
  - Emit rows with exactly the declared fields from source_field, lookup_field,
    or literal value specs.
- Typed CSV upload semantics:
  - file_schema columns are part of the public contract.
  - Do not infer all uploaded values as strings when a column is declared as
    number or boolean.
  - The public input.rows-equivalent state should match those declared types.
- Keep the UI usable and visually clear.
- Do not include tests, scenarios, evaluator code, or hard-coded scenario
  responses.

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
    {{"path": "index.html", "content": "..."}},
    {{"path": "styles.css", "content": "..."}},
    {{"path": "app.js", "content": "..."}}
  ],
  "notes": "short implementation summary"
}}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a blind static app from ConformWeb public inputs.")
    parser.add_argument("--contract-dsl", type=Path, required=True)
    parser.add_argument(
        "--public-scenarios-dsl",
        type=Path,
        action="append",
        help=(
            "Optional public scenario DSL file to include in the blind prompt. "
            "May be supplied more than once. Private scenarios must not be supplied."
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--provider", choices=["openai", "anthropic", "google"], default="openai")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument(
        "--base-url",
        help="Optional provider API base URL. Anthropic paper cohorts should pass https://api.anthropic.com.",
    )
    parser.add_argument("--max-output-tokens", type=int, default=24000)
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=240,
        help="Provider HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--member-id",
        help="Optional model cohort member id recorded in generation metadata.",
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        help="Optional path for generation metadata JSON. Defaults to <output-dir>/generation.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contract_text = args.contract_dsl.read_text(encoding="utf-8")
    public_scenarios_text = public_scenarios_section(args.public_scenarios_dsl or [])
    prompt = PROMPT.format(
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
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = {"index.html", "styles.css", "app.js"}
    received = {item["path"] for item in payload["files"]}
    if received != expected:
        raise SystemExit(f"Model returned unexpected file set: {sorted(received)}")

    for file in payload["files"]:
        destination = output_dir / file["path"]
        destination.write_text(file["content"], encoding="utf-8")

    (output_dir / "GENERATION.md").write_text(
        "# Blind DSL Generation\n\n"
        f"Provider: `{args.provider}`\n\n"
        f"Model: `{args.model}`\n\n"
        f"Cohort member: `{args.member_id or 'ad-hoc'}`\n\n"
        f"Contract SHA-256: `{contract_sha}`\n\n"
        f"Prompt SHA-256: `{prompt_sha}`\n\n"
        f"Variant: {args.variant}\n\n"
        f"{payload['notes']}\n",
        encoding="utf-8",
    )
    metadata = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generator": "tools/generate_blind_dsl_static_app.py",
        "member_id": args.member_id,
        "provider": args.provider,
        "model": args.model,
        "base_url": redacted_base_url(args.base_url),
        "max_output_tokens": args.max_output_tokens,
        "request_timeout": args.request_timeout,
        "variant": args.variant,
        "contract_path": str(args.contract_dsl.resolve()),
        "public_scenarios_paths": [
            str(path.resolve())
            for path in (args.public_scenarios_dsl or [])
        ],
        "contract_sha256": contract_sha,
        "prompt_sha256": prompt_sha,
        "output_dir": str(output_dir.resolve()),
        "response": response_metadata,
        "git_commit": current_git_commit(),
        "files": sorted(received),
        "notes": payload["notes"],
    }
    metadata_path = args.metadata_output or output_dir / "generation.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "written": sorted(received),
                "metadata": str(metadata_path),
                "notes": payload["notes"],
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


def public_scenarios_section(paths: list[Path]) -> str:
    if not paths:
        return (
            "No public scenario examples are provided. Do not invent hidden "
            "scenario answers."
        )
    parts = [
        "Public DSL scenario examples are provided below. These are public "
        "behavior examples only; do not hard-code scenario scripts or assume "
        "access to private scenarios."
    ]
    for path in paths:
        parts.append(
            f"\nPublic scenario file: {path.name}\n```yaml\n"
            f"{path.read_text(encoding='utf-8')}\n```"
        )
    return "\n".join(parts)


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
                "name": "static_app",
                "strict": True,
                "schema": response_schema(),
            }
        },
    )
    return json.loads(extract_json_payload(response.output_text)), {"id": getattr(response, "id", None)}


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
    response = post_json(
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
    return json.loads(extract_json_payload(text)), {
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
    response = post_json(
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
    return json.loads(extract_json_payload(text)), {
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
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["files", "notes"],
    }


def post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict,
    redacted_url: str,
    timeout: int = 240,
) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"POST {redacted_url} failed: HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"POST {redacted_url} failed: {error}") from error


def extract_json_payload(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise SystemExit("Model returned an empty response")
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass
    try:
        _, end = json.JSONDecoder().raw_decode(stripped)
        return stripped[:end]
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    if fence:
        fenced = fence.group(1).strip()
        try:
            _, end = json.JSONDecoder().raw_decode(fenced)
            return fenced[:end]
        except json.JSONDecodeError:
            return fenced
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    raise SystemExit(f"Could not extract JSON payload from model response: {stripped[:500]}")


def redacted_base_url(base_url: str | None) -> str | None:
    if not base_url:
        return None
    return base_url.split("?key=", 1)[0] + ("?key=***" if "?key=" in base_url else "")


def current_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001 - metadata should not block generation.
        return None
    return result.stdout.strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
