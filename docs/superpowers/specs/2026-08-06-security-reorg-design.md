# Design: Reorganize `vibemind-os/security`

**Date:** 2026-08-06
**Author:** Claude (Fable 5) session, on behalf of Felix (@Flissel)
**Status:** Awaiting user review

## Problem

`vibemind-os/security/` (218 tracked files) is not maintainable:

1. **The README lies.** It advertises a clean "VibeMind Security Lab" with 30 modules
   under `pocs/` + `infra/` and a public repo `github.com/Flissel/vibemind-security`.
   None of that layout exists on disk — the real tree is ~50 flat `poc_*` dirs.
2. **It conflates three unrelated concerns** under one "security" label: real security
   tooling, offensive/adversarial PoCs, and ~24 generic AutoGen/MCP agent demos that
   are not security at all.
3. **It carries cruft in version control:** 7 `*.backup` files, 3 `agent_new.py`
   duplicates, `README.txt`/`README.md` duplicate pairs, 14 `*.html` reports, and 14
   `.scan_history/*.json` dumps of **real domains** (`www.bnd.bund.de`,
   `edwardsnowden.substack.com`, `x.com`) — against a README that claims a public repo.
4. **Phantom modules.** `poc_os_shield`, `poc_log_analyzer`, `poc_red_blue` have **zero
   tracked files**, yet the README and `_test_all_pocs.py` reference them.
5. **Stale git linkage.** An orphaned `.git` file inside `security/` points at a
   non-existent gitdir (`../.git/modules/security`). `security/` is actually tracked as
   a plain directory inside `vibemind-os` — NOT a submodule. So `git mv` inside
   `vibemind-os` preserves history cleanly.

## Goals

- One folder = one concern. `security/` holds only real security work.
- Consistent, prefix-free naming: `security/pocs/<category>/<name>/`.
- Remove committed cruft and sensitive scan dumps from the working tree.
- An honest README that matches the tree.
- Preserve git history for every moved file (`git mv`).

## Non-goals

- Rewriting git history to scrub the sensitive scan data from past commits. Removing it
  from the working tree is in scope; a full `git filter-repo` history scrub is a
  separate, riskier operation flagged at the end (see "Open risk: git history").
- Rewriting or refactoring the PoC code itself. This pass only moves, renames, deletes,
  and re-documents.
- Fixing the phantom modules' missing code. We only stop referencing non-existent code.

## Decisions (from user, 2026-08-06)

1. Plan first (this doc), then execute.
2. The generic agent/MCP demos leave `security/` entirely.
3. Purge the scan data from the tree + add gitignore rules.
4. Layout convention: `pocs/<category>/<name>/`, `poc_` prefix dropped.

## Target layout

```
vibemind-os/
  security/
    README.md              # rewritten to match reality
    SECURITY.md            # kept
    LICENSE                # kept
    requirements.txt       # kept
    llm_client.py          # shared LLM access, kept at root
    llm_config.yml         # kept (currently gitignored — see note)
    run_tests.py           # renamed from _test_all_pocs.py, phantom refs removed
    pocs/
      defense/
        vuln_scanner/
        network_monitor/
        forensics/
        canary/
        botnet_detector/
        firewall/
        event_log/
        endpoint_hardening/
        alerter/
        pc_monitor/
        storage_manager/
      offense/
        site_verifier/     # scan_history/ + *.html reports removed
        injection_chain/   # was the loose poc_injection_chain.py
        captcha_eval/      # browser-agent security eval on own infra
      infra/
        grpc_host/
        keycloak/

  examples/
    mcp-agents/            # NEW home for the non-security agent/MCP demos
      fetch/  github/  git/  time/  redis/  qdrant/  postgres/  supabase/
      tavily/  taskmanager/  playwright/  desktop/  context7/  brave_search/
      memory/  n8n/  filesystem/  supermemory/  claude_code/  windows_core/
      chat_orchestrator/  automation_ui_bridge/  nemoclaw/  fungus_mcp/
```

## Complete move / rename map

### A. Stay in `security/`, move under `pocs/<category>/` (drop `poc_` prefix)

| From | To |
|---|---|
| `poc_vuln_scanner/` | `pocs/defense/vuln_scanner/` |
| `poc_network_monitor/` | `pocs/defense/network_monitor/` |
| `poc_forensics/` | `pocs/defense/forensics/` |
| `poc_canary/` | `pocs/defense/canary/` |
| `poc_botnet_detector/` | `pocs/defense/botnet_detector/` |
| `poc_firewall/` | `pocs/defense/firewall/` |
| `poc_event_log/` | `pocs/defense/event_log/` |
| `poc_endpoint_hardening/` | `pocs/defense/endpoint_hardening/` |
| `poc_alerter/` | `pocs/defense/alerter/` |
| `poc_pc_monitor/` | `pocs/defense/pc_monitor/` |
| `poc_storage_manager/` | `pocs/defense/storage_manager/` |
| `poc_site_verifier/` | `pocs/offense/site_verifier/` |
| `poc_injection_chain.py` | `pocs/offense/injection_chain/injection_chain.py` |
| `poc_captcha_eval/` | `pocs/offense/captcha_eval/` |
| `poc_grpc_host/` | `pocs/infra/grpc_host/` |
| `poc_keycloak/` | `pocs/infra/keycloak/` |

### B. Leave `security/` → `vibemind-os/examples/mcp-agents/<name>/`

`poc_fetch`, `poc_github`, `poc_git`, `poc_time`, `poc_redis`, `poc_qdrant`,
`poc_postgres`, `poc_supabase`, `poc_tavily`, `poc_taskmanager`, `poc_playwright`,
`poc_desktop`, `poc_context7`, `poc_brave_search`, `poc_memory`, `poc_n8n`,
`poc_filesystem`, `poc_supermemory`, `poc_claude_code`, `poc_windows_core`,
`poc_chat_orchestrator`, `poc_automation_ui_bridge`, `poc_nemoclaw`, `poc_fungus_mcp`
→ each becomes `examples/mcp-agents/<name>/` (prefix dropped).

### C. Delete (cruft — `git rm`)

- `**/*.backup` (7 files): `poc_brave_search/agent.py.backup`, `poc_desktop/…`,
  `poc_filesystem/…`, `poc_memory/…`, `poc_redis/…`, `poc_supabase/…`,
  `poc_windows_core/…`.
- Orphaned `security/.git` file (not tracked — just remove from working tree).
- `README.txt` where a `README.md` exists in the same dir (dedupe):
  `poc_context7/`, `poc_desktop/`, `poc_redis/`, `poc_supabase/`.

### D. Reconcile, don't blind-delete

- `agent_new.py` vs `agent.py` in `poc_context7/`, `poc_desktop/`, `poc_redis/`:
  diff the two, keep the current one, delete the stale one, and (if `_new` is the live
  one) rename it to `agent.py`. One decision per dir during execution.

### E. Purge sensitive / generated artifacts (`git rm` + gitignore)

- `poc_site_verifier/.scan_history/*.json` (14)
- `poc_site_verifier/*.html` reports (14)
- Add to `security/.gitignore`: `.scan_history/`, `pocs/offense/site_verifier/*.html`,
  `report_*.html`, `attack_chain_*.html`.

### F. Phantom modules

`poc_os_shield/`, `poc_log_analyzer/`, `poc_red_blue/` have no tracked source. Action:
remove them from `README.md` and `_test_all_pocs.py` references; leave the on-disk
(gitignored) contents untouched. If the user confirms the code should exist, that's a
follow-up, not this pass.

### G. Loose root scripts (not security)

~17 root scripts unrelated to the security lab — `train_brain.py`,
`train_brain_complete.py`, `train_brain_multilingual.py`, `test_agents.py`,
`test_all_live.py`, `test_all_spaces.py`, `test_brain_all_spaces.py`,
`test_briefing_live.py`, `test_find_network.py`, `test_groq_large.py`,
`test_live_intents.py`, `test_mailcow_smtp.py`, `test_one_intent.py`,
`test_spaces_slow.py`, `test_video_live.py`. **Proposed:** move to
`vibemind-os/tests/legacy-brain/` (or delete if dead). Flagged for the user to confirm —
these look like they were dumped here and belong with the brain/spaces test suites.
`_test_all_pocs.py` stays (renamed `run_tests.py`, phantom refs removed).

## Reference updates required after the move

**CRITICAL — live OpenFang coupling.** Pre-flight grep found that six security PoCs are
registered as **live MCP servers** in the OpenFang config. `openfang.vibemind.toml.template`
launches them by absolute path:

```
security/poc_network_monitor/mcp_server.py
security/poc_endpoint_hardening/mcp_server.py
security/poc_event_log/mcp_server.py
security/poc_firewall/mcp_server.py
security/poc_botnet_detector/mcp_server.py
security/poc_site_verifier/mcp_server.py
```

Moving these dirs to `pocs/defense/…` and `pocs/offense/…` **breaks the running agent
stack** unless the template paths are updated in the SAME commit as the move. `openfang/
VIBEMIND_INTEGRATION.md` documents the same six paths and must be updated too. This turns
"move the security PoCs" into a coupled change across two repos (`vibemind-os` +
outer `openfang/`) — sequence it carefully and restart OpenFang after (per the OpenFang
restart runbook: `.env`/`secrets.env` first, then restart), then verify one MCP call.

- `openfang.vibemind.toml.template` + `VIBEMIND_INTEGRATION.md`: rewrite the 6 paths.
  (The `.bak-pre-brain-gateway-fix` copy is stale — leave it, or delete it as cruft.)
- `_test_all_pocs.py` → `run_tests.py`: update `os.path.join(BASE, 'poc_x', …)` paths to
  `pocs/<cat>/<name>/…`; drop phantom modules.
- `security/README.md` + `poc_captcha_eval/README.md`: fix `cd` paths and rewrite Project
  Structure + Usage to the real tree; drop the `python -m pocs.network_monitor`
  invocations that never worked.

**Out-of-scope duplication noted:** `docs/archive/dead_code_report.md` records parallel
`ops/poc_red_blue/`, `ops/poc_docker/`, `ops/poc_log_analyzer/`, `ops/poc_os_shield/`,
`ops/poc_security_scanner/` dirs that appear to duplicate security PoCs. Not touched by
this pass — flagged as a separate cleanup.

## Execution plan (phased, each phase = its own commit)

0. **Pre-flight:** `grep -rn "security/poc_" vibemind-os` (and outer repo) to catch
   external references. If any exist, adjust scope before moving.
1. **Purge cruft + sensitive data** (`git rm` backups, README.txt dupes, scan_history,
   html reports; delete orphaned `.git`; add gitignore rules). Commit.
2. **Create `pocs/{defense,offense,infra}/` and `git mv` the security PoCs.** Commit.
3. **Reconcile `agent_new.py` duplicates.** Commit.
4. **Create `examples/mcp-agents/` and `git mv` the 24 agent demos out.** Commit.
5. **Move/retire loose root scripts** (per user confirmation on G). Commit.
6. **Fix `run_tests.py` paths + rewrite `README.md`.** Run `python run_tests.py` to
   confirm the security PoCs still import. Commit.

Each phase is a small, reviewable commit directly on `master` (per repo CLAUDE.md), so
any step is trivially revertible.

## Open risk: git history

The sensitive scan data (`bnd.bund.de` etc.) will remain in **git history** after step 1
removes it from the tree. If `security/` was ever pushed to the public
`github.com/Flissel/vibemind-security`, the data is already exposed and a working-tree
delete does not undo that. Recommended follow-up (out of scope here, needs explicit go):
confirm whether it reached the public remote; if so, rotate/retract and consider a
history rewrite. Tracked as a separate decision.

## Notes

- `llm_config.yml` currently shows as **gitignored** (`!!`) in status but a copy is on
  disk. Confirm whether it should be tracked; it holds LLM routing config, no secrets
  expected — but verify no keys before committing.
- WORKBOARD: this touches a shared area of `vibemind-os`. Claim in `WORKBOARD.md` before
  executing (repo protocol).
