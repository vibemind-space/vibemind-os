# ops — operations & dev-agent PoCs

AutoGen/gRPC agent experiments and operational tooling for VibeMind. Security-focused
PoCs that used to live here (os_shield, log_analyzer, security_scanner, red_blue,
site_verifier, injection_chain) were consolidated into `../security/` on 2026-08-06;
this directory keeps the dev/ops agent work.

## Layout

```
ops/
  llm_client.py            # shared LLM access (shim to vibemind_shared)
  llm_config.yml           # LLM routing config (gitignored)
  requirements.txt
  pocs/                    # AutoGen agent PoCs
    codegen/               # code-generation agent over gRPC
    distributed/           # distributed AutoGen runtime (GrpcWorkerAgentRuntimeHost :50051)
    docker/                # agent attack-demo (DB scenario)
    git_agents/            # git automation agents (board/CI-CD/review/triage) + orchestrator
  git_agent/               # gh CLI auth setup + smoke scripts (PowerShell)
  pc-cleaner/              # disk/storage inspection + safe cleanup (MCP server)
  mcp/                     # MCP server registry
  scripts/                 # orchestration entry points (e.g. EventFixTeam)
  docs/
```

## Notes

- Each `pocs/<name>/` is self-contained; `git_agents` imports the shared `llm_client`
  from the ops root (`../..`).
- The `poc_` directory prefix was dropped in the 2026-08-06 reorg.
