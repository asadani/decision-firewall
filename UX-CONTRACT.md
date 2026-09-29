# Inspector interaction contract

## Business context

| Concern | Source | UI consequence |
|---|---|---|
| Refund policy and money | docs/product.md | Display amount and original payment; approval never promises execution |
| Authority and local roles | docs/threat-model.md | Fixed local reviewer; no user-entered role elevation |
| Lifecycle and idempotency | docs/architecture.md | Show request state separately from attempts; prevent duplicate review submit |
| Legal claims | docs/product.md | Explicit demonstration policy; no compliance certification |
| Privacy | docs/threat-model.md | Synthetic records only; exports are whole local audit chains |

## Canonical ownership

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | native select in list.html | DESIGN.md | OS-owned popup | Browser keyboard and opened popup |
| Form | detail.html and app.js | review API and this contract | review | tests/test_web.py and browser QA |
| Scrollbar | app.css global rules | DESIGN.md | vertical document / horizontal table | Browser computed style |
| Toast | persistent inline notice in shared templates | this contract | success/error/status | Browser + response tests |
| CRUD | web.py plus Firewall service | docs/architecture.md | list/detail/review | tests/test_web.py |

No table selection or date input exists. Request creation is CLI/SDK-owned. No browser delete or payment execution capability exists.

## Flow ledger

- List: committed search/status/page in URL; explicit Apply filters avoids request races; clear submits immediately. Ten rows per page, newest first. Empty and no-results states provide a route back.
- Detail: evidence, model assessment, policy snapshot, attempt status, and signed event timeline. JSON is escaped and wrapped.
- Review: reason required; current revision included; pending blocks duplicate submit. Success redirects to the same detail with a persistent notice. Validation/stale failures retain reason and focus the error. The backend validates authority and policy again.
- Request evidence: returns to detail with missing evidence visible. Evidence updates are trusted SDK operations, not editable model claims.
- Unknown execution: show unresolved status and reconciliation guidance. Never offer an unchecked retry button.
- Runs: group by run, separate model accuracy/policy agreement/gate latency, expose full manifests and missing values.

## Resilience and accessibility

Native links/buttons/forms/tables, associated labels, visible focus, live status, no color-only states. All product forms use novalidate and application feedback. Native select popup geometry is intentionally OS-owned. Textareas auto-grow and cannot resize manually. Dirty review text uses the browser's narrow unload safeguard; there are no destructive application dialogs. Explicit full-page submissions avoid optimistic success and stale async rendering. HTTP failure responses remain navigable.

English interface; INR labels and UTC audit timestamps are explicit. Desktop and narrow layouts share components. Reduced motion, forced colors, and print styles are supported. Browser verification covers empty/error, review success/stale/validation, keyboard, open select, narrow detail, and evaluation views.

