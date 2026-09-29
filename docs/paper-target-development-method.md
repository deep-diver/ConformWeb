# Paper Target Development Method

Date: 2026-05-11

This document records the current paper-facing workflow for constructing one
DetoxBench target. The goal is to build realistic web applications that are
usable as products, while still keeping evaluation fair: the candidate receives
the public contract and disclosed public scenarios, not the reference
implementation or private scenario answers.

## Protocol

1. Pick a broad target domain.
2. Design a target app that looks and behaves like a plausible commercial
   service, not like a state-debugging dashboard.
3. Author a DSL 3.0 `contract.dsl.yaml` for the core behavior surface.
4. Author tiered public/private scenario DSL files that exercise simple,
   core, validation, service, upload, permission, persistence, and end-to-end
   journeys.
5. Compile the contract and scenarios into a deterministic evaluator.
6. Generate or implement one reference app using the contract and public
   scenarios only. The reference must pass the full evaluator, including
   private scenarios, after iterative repair.
7. Generate blind implementations from weaker models first, using the public
   contract and disclosed public scenarios.
8. Evaluate blind implementations, record formal score, stepwise score,
   contract score, tier breakdown, first failed step, failure category, and
   screenshots.
9. Move upward through stronger model cohorts until the frontier cohort has
   also been evaluated.

## Disclosure Boundary

Blind implementations may receive:

- the public DSL contract;
- the disclosed public scenario file;
- the target domain and product premise;
- a request for polished, production-quality UI/UX comparable to a real
  commercial service.

Blind implementations must not receive:

- the reference app source;
- reference screenshots;
- private scenario files;
- evaluator logs, run summaries, dashboard artifacts, or failure answers.

The UI/UX request is fair because visual realism is not a hidden scenario
answer. It asks the model to build a plausible product surface while still
requiring the implementation to satisfy the public behavioral contract.

## Model Tiers

The current target-development loop starts with Model Tier M and climbs toward
Model Tier F. The canonical tier definitions live in `docs/model-tiers.md`.

| Model Tier | Example models | Purpose |
| --- | --- | --- |
| M | GPT-5.4 nano, Claude Haiku 4.5, Gemini 3.1 Flash Light/Lite | Confirm that the target surfaces obvious implementation failures. |
| T | GPT-5.4 mini, Claude Sonnet 4.6, Gemini Flash latest proxy | Check whether intermediate models recover core behavior but fail deeper flows. |
| F | GPT-5.4, Claude Opus 4.6, Gemini 3.1 Pro Preview | Establish the paper-facing difficulty frontier. |

## Why Product UI Matters

Earlier state-oriented targets often behaved like dashboards: most controls and
state values were exposed directly, so blind implementations could pass by
rendering a flat control panel around the public state object. The current
method deliberately asks for a realistic service UI. This creates a harder and
more paper-relevant pressure surface:

- controls may be distributed across pages, panels, and product flows;
- UI actionability matters, not just DOM presence;
- formatted product copy can accidentally violate raw table-cell contracts;
- route persistence, hidden panels, and role-gated controls become real failure
  modes;
- the model must balance visual polish with exact behavioral semantics.

The evaluator still scores public behavior, not aesthetic taste. The reference
app is productized so the target is credible for a paper appendix, and blind
apps are asked to pursue similar visual quality without seeing the reference.

## Initial Baseline: StayFlow Concierge Tier A

`targets/web/stayflow_concierge/tier_a` is the current starting point for this
method. It is a consumer travel booking and concierge workflow implemented
under DSL 3.0.

Tier A covers:

- three routes: discover/search, checkout, and concierge/manage;
- catalog filtering and stay selection;
- add-on pricing and total recomputation;
- promo service validation;
- guest validation;
- CSV group manifest upload;
- agent role confirmation and unauthorized guest attempts;
- reload persistence and browser history checks.

Reference status:

| Subject | Scenarios | Formal | Stepwise | Contract |
| --- | ---: | ---: | ---: | ---: |
| `reference_all` | 23 / 23 | 100% | 100% | 100% |

Blind cohort summary:

| Model Tier | Subject | Scenarios | Formal | Stepwise | Contract |
| --- | --- | ---: | ---: | ---: | ---: |
| M | `blind_gpt54_nano_01` | 17 / 23 | 71% | 85% | 78% |
| M | `blind_claude_haiku45_01` | 0 / 23 | 0% | 10% | 100% |
| M | `blind_gemini31_flash_lite_01` | 0 / 23 | 0% | 10% | 100% |
| T | `blind_gpt54_mini_01` | 0 / 23 | 0% | 10% | 100% |
| T | `blind_claude_sonnet46_01` | 13 / 23 | 54% | 82% | 78% |
| T | `blind_gemini_flash_latest_01` | 0 / 23 | 0% | 10% | 100% |
| F | `blind_gpt54_01` | 17 / 23 | 70% | 85% | 78% |
| F | `blind_claude_opus46_01` | 17 / 23 | 73% | 85% | 78% |
| F | `blind_gemini31_pro_preview_01` | 7 / 23 | 28% | 67% | 39% |

The key observed failure class is not a hidden evaluator trick. Several blind
apps create required controls in the DOM but hide them at the moment the
scenario needs to use them. This is a product-flow/actionability failure: the
public contract names the control, but the implementation fails to make that
control usable across the required route and state combinations.

Detailed StayFlow records:

- `targets/web/stayflow_concierge/tier_a/README.md`
- `targets/web/stayflow_concierge/tier_a/cohort-tier-a-lower-models.md`
- `targets/web/stayflow_concierge/tier_a/cohort-tier-a-upper-models.md`
- `targets/web/stayflow_concierge/tier_a/cohort-tier-a-frontier-models.md`

## StayFlow Concierge Tier B

`targets/web/stayflow_concierge/tier_b` is the next separate StayFlow tier,
not a replacement for Tier A. It keeps the same public-contract-only blind
disclosure rule while increasing the behavioral state space.

Tier B adds:

- ordered multi-city itinerary legs;
- per-leg add-ons and route-level fee recomputation;
- quote and promo service interactions;
- traveler manifest upload with derived child and mobility counters;
- stronger role-gated agent checklist behavior;
- longer full-journey scenarios spanning builder, quote, travelers, and ops.

Reference status:

| Subject | Scenarios | Formal | Stepwise | Contract |
| --- | ---: | ---: | ---: | ---: |
| `reference_all` | 29 / 29 | 100% | 100% | 100% |

Detailed Tier B record:

- `targets/web/stayflow_concierge/tier_b/README.md`

Tier C should grow from this by adding still broader state-space, deeper
cross-page coupling, and longer scenario ladders while preserving the same
public-contract-only blind disclosure rule.
