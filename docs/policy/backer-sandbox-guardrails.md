# Backer-Sandbox Guardrails — kanonische Policy (POL-0, Phase 0)

> Stand 2026-07-02 · Status: **verbindlich** ab Phase 0.
> Diese Policy gilt für jeden Backer-/Distributions-/Payment-Code, der in
> diesem Baum (`vibemind-os/`, Branch `feat/mcp-tool-hub`) gebaut wird —
> insbesondere das in Phase 2 entstehende `backer-checkout/`
> (`ledger.py`, `distribute.py`, `generate_links.py`, `outbox/`).
> Referenz-Anti-Patterns stammen aus dem OS-Snapshot
> (`C:/Users/User/Desktop/VibeMind-OS/backer-checkout/`) — dieser Code
> existiert in V1 **nicht** und wird hier nur als Negativbeispiel zitiert.
>
> Übergeordnete Regel (CASCADE §1.4, nicht verhandelbar): **Keine reale
> Outreach/Zustellung und keine Bewegung echten Geldes, bis alles in
> Sandbox/Dry-Run getestet ist.** Fail-closed: fehlt eine Guardrail-Quelle,
> wirft das System — es fällt NIE still auf einen schwächeren Modus zurück.

---

## Guardrail 1 — `paypal_env_fail_closed`

**Regel:** `PAYPAL_ENV` hat **keinen Default**. Es wird an drei Grenzen
validiert: (1) beim Boot, (2) vor jedem Hop-Dispatch, (3) unmittelbar vor
jedem `requests.post` an PayPal (`create_order`/`capture_order`). Erlaubte
Werte: exakt `sandbox` oder `live`. Fehlt/leer/anderer Wert →
`PayPalEnvError`, kein PayPal-Call wird abgesetzt. `live` ist nur erreichbar
über ein explizites, out-of-band gesetztes Human-Freigabe-Token, das die
autonome Schleife nicht selbst erzeugen kann.

**Anti-Pattern (OS-Referenz):** `app.py:44` liest
`os.environ.get("PAYPAL_ENV", "sandbox")` — ein stiller Soft-Default ohne
Assertion. `paypal_client.py:21-24` hält BEIDE Basis-URLs (sandbox UND live)
hardcodet vor; ein Tippfehler in der Env genügt dort, um die Live-URL zu
erreichen.

**Enforcement:** `tests/policy/test_env_guard.py` (Phase-2 ENFORCEMENT,
skipif-absent — siehe `test_activation_mechanism`).

---

## Guardrail 2 — `live_transport_import_ban`

**Regel:** Der Sandbox-Distributionspfad (`distribute.py` und alles, was die
Such-/Registry-/Evolutionsschicht erreichen kann) darf **keine**
Live-Transport-Symbole importieren: `requests`, `smtplib`, `http`, `socket`,
`paypal`. Zustellung im Dry-Run ist ausschließlich Datei-basiert
(`outbox/`-Previews). Payment-Code lebt quarantäniert in `backer-checkout/`
und ist von der Sandbox-Registry aus **nicht repräsentierbar** (Live-IDs sind
in der Registry ABWESEND, nicht bloß dispatch-zeitlich verboten). Ein
Versand-Versuch aus der Sandbox heraus muss **crashen** (positiv beweisbares
Zero-Send-Veto), nicht still gelingen.

**Enforcement:** `tests/policy/test_no_live_transport_in_sandbox.py` —
AST-basierter Import-Scan + Raw-Grep, Assert: Treffer-Menge leer.
`backer-checkout/` selbst steht auf der Allowlist (es IST der quarantänierte
Payment-Code). Authored in Phase 0 als `xfail(strict=True)`.

---

## Guardrail 3 — `idempotency_ledger_caps`

**Regel:** Jeder PayPal-Order-Call trägt einen deterministischen
`PayPal-Request-Id`-Header (Idempotency-Key = Hash aus
`run_id + recipient + amount`), sodass Retries nie Doppel-Orders erzeugen.
Das Ledger (`ledger.py`, Phase 2) erzwingt `UNIQUE(order_id)` und einen
Unique-Index auf dem Idempotency-Key. `MAX_ORDERS_PER_RUN` (env-konfigurierbar,
**Default: 25** — Policy-Entscheidung POL-0) wird VOR jedem PayPal-Call
geprüft; Überschreitung → HTTP 429, kein Order. Ein Empfänger = maximal ein
offener Order pro Run. Caps gelten AUCH in Sandbox.

**Anti-Pattern (OS-Referenz):** `paypal_client.py` `create_order` (`:76-97`)
sendet keinen `PayPal-Request-Id`-Header; es existiert kein Ledger, kein Cap,
kein Rate-Limit in der Routing-Ebene.

**Enforcement:** `tests/policy/test_idempotency_ledger.py` (Phase-2
ENFORCEMENT, skipif-absent).

---

## Guardrail 4 — `deterministic_env_file`

**Regel:** Payment-relevante Credentials werden aus GENAU einer, explizit
benannten Datei geladen: `BACKER_ENV_FILE` (absoluter Pfad, muss gesetzt
sein). Kein `find_dotenv(usecwd=True)`-Walk-up, kein Fallback auf
Sibling-Repos. Beim Start werden der aufgelöste absolute Pfad und das
aufgelöste `PAYPAL_ENV` geloggt. `BACKER_ENV_FILE` unset/fehlend →
fail-closed Raise.

**Anti-Pattern (OS-Referenz):** `app.py:29-33` — 4-Wege-Auflösungskette
inklusive Fallback auf `x-pathfinder/.env` im Schwester-Repo (das dort real
`PAYPAL_SECRET` enthält). Credential-Herkunft ist damit
arbeitsverzeichnis-abhängig und nicht auditierbar.

**Enforcement:** `tests/policy/test_env_file_resolution.py` (Phase-2
ENFORCEMENT, skipif-absent). Ehrliche Einordnung: das Sibling-Anti-Pattern
ist in V1 nicht exerzierbar — der Test ist eine vorinstallierte Falle, kein
Bug-Beweis.

---

## Guardrail 5 — `port_collision`

**Regel:** Die Payment-Flask-App bindet **nie** den Brain-Port. Default-Port
der Payment-App: **5055** (nicht 5000). Boot-Assertion:
`(payment_host, payment_port) != (brain_host, brain_port)`, wobei
Brain-Host:Port aus derselben Config-Quelle gelesen wird wie im Orchestrator
(`brain_shadow.py:31` → heute `http://localhost:5000`) — nicht hardcodet.
Kollision → `PortCollisionError` beim Boot.

**Anti-Pattern (OS-Referenz):** OS `app.py:95` Flask-Default `PORT=5000`
kollidiert mit dem `BrainShadowObserver`-Default `localhost:5000` — zwei
Dienste auf demselben Port, stilles First-come-first-served.

**Enforcement:** `tests/policy/test_port_collision.py` (Phase-2 ENFORCEMENT,
skipif-absent).

---

## Test-Aktivierungs-Mechanismus — `test_activation_mechanism`

Alle WS4-Tests liegen unter `tests/policy/`. **Kein** `backer-checkout/`-
Verzeichnis wird in Phase 0 angelegt (kein Vaporware-Scaffolding). Damit die
Gesamt-Suite in Phase 0/1 grün bleibt und die Guardrails sich in Phase 2
automatisch scharf schalten:

| Test | Mechanismus | Verhalten |
|---|---|---|
| `test_guardrail_policy_present.py` | aktiv | Einziger WS4-Test, der in Phase 0 GREEN ist (prüft dieses Doc + 6 Anker). |
| `test_env_guard.py`, `test_idempotency_ledger.py`, `test_env_file_resolution.py`, `test_port_collision.py` | `pytest.mark.skipif(not (REPO_ROOT / 'backer-checkout').exists(), reason='Phase-2 ENFORCEMENT — backer-checkout absent (POL-0)')` | Heute SKIP (red-by-absence, keine Bug-Beweise). Sobald Phase 2 `backer-checkout/` anlegt, laufen sie automatisch und MÜSSEN bestehen. |
| `test_no_live_transport_in_sandbox.py` | `pytest.mark.xfail(strict=True, reason='Phase-2 — distribute.py absent; XPASS erzwingt Marker-Entfernung')` | Discovery-Assert failt heute → XFAIL (Suite grün). Landet `distribute.py` und der Scan besteht → XPASS → `strict=True` macht das zum lauten Fehler → Marker wird entfernt, Test wird permanenter Gate. |

**Regel:** Ein Phase-2-PR, der `backer-checkout/` anlegt, darf keinen dieser
Tests löschen oder dauerhaft skippen — Aktivierung ist der Sinn des
Mechanismus. Marker-Entfernung bei IMPORT-2 ist Teil des Phase-2-PRs.

---

## Referenzen

- CASCADE-BANDIT Design: `backer-checkout/docs/superpowers/specs/2026-07-02-cascade-bandit-orchestrator-design.md` (OS-Baum, §1.4 Guardrail, §7.1 Befunde)
- Integrations-Design: `brain/the_brain/docs/plans/2026-07-02-cascade-integration-design.md` (§5.5, §6 Phase 0/2)
- Phase-0-Bauplan: `brain/the_brain/docs/plans/2026-07-02-phase0-build-plan.md` (POL-0, ENV-1, IMPORT-2, IDEM-3, ENVFILE-4, PORT-5)
