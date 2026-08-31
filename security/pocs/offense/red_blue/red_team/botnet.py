"""
Red Team Botnet Simulator
============================
Simulates multiple concurrent attackers hitting the system simultaneously.

Modes:
  - sequential: One attack at a time (classic, default)
  - wave: Attacks in timed waves (2-3 parallel per wave)
  - swarm: All attacks fire at once (maximum pressure)
  - coordinated: Sequential phases, parallel within each phase

Uses asyncio.gather for true parallel execution of attack tools.
Each "bot" is an independent attack coroutine.
"""

import asyncio
import json
import random
import time
from datetime import datetime


# ================================================================
# BOT IDENTITIES (for realistic log output)
# ================================================================

BOT_NAMES = [
    "GHOST-01", "PHANTOM-02", "SHADOW-03", "SPECTRE-04",
    "WRAITH-05", "RAVEN-06", "VIPER-07", "COBRA-08",
    "HYDRA-09", "KRAKEN-10", "REAPER-11", "STORM-12",
]


def _get_bot_name(index: int) -> str:
    return BOT_NAMES[index % len(BOT_NAMES)]


# ================================================================
# BOTNET EXECUTION MODES
# ================================================================

async def execute_sequential(attack_fn, tool_calls: list[dict]) -> list[dict]:
    """Classic mode: one attack after another.

    Args:
        attack_fn: async callable(tool_name, args) -> result dict
        tool_calls: list of {"tool": str, "args": dict}
    """
    results = []
    for i, call in enumerate(tool_calls):
        bot = _get_bot_name(i)
        print(f"    [{bot}] -> {call['tool']}", flush=True)
        start = time.time()
        result = await attack_fn(call["tool"], call.get("args", {}))
        elapsed = round(time.time() - start, 1)
        result["bot"] = bot
        result["elapsed_seconds"] = elapsed
        results.append(result)
        print(f"    [{bot}]    done ({elapsed}s)", flush=True)
    return results


async def execute_wave(attack_fn, tool_calls: list[dict],
                       wave_size: int = 3, wave_pause: float = 2.0) -> list[dict]:
    """Wave mode: attacks in timed waves of parallel execution.

    Args:
        attack_fn: async callable(tool_name, args) -> result dict
        tool_calls: list of {"tool": str, "args": dict}
        wave_size: number of parallel attacks per wave (default: 3)
        wave_pause: seconds between waves (default: 2.0)
    """
    results = []
    wave_num = 0

    for i in range(0, len(tool_calls), wave_size):
        wave = tool_calls[i:i + wave_size]
        wave_num += 1
        bots = [_get_bot_name(i + j) for j in range(len(wave))]

        print(f"    === WAVE {wave_num}: {', '.join(bots)} ===", flush=True)
        for j, call in enumerate(wave):
            print(f"    [{bots[j]}] -> {call['tool']}", flush=True)

        start = time.time()

        async def _run_bot(idx, call, bot_name):
            result = await attack_fn(call["tool"], call.get("args", {}))
            result["bot"] = bot_name
            result["wave"] = wave_num
            return result

        wave_results = await asyncio.gather(
            *[_run_bot(j, call, bots[j]) for j, call in enumerate(wave)],
            return_exceptions=True,
        )

        elapsed = round(time.time() - start, 1)

        for wr in wave_results:
            if isinstance(wr, Exception):
                results.append({"bot": "ERROR", "error": str(wr), "wave": wave_num})
            else:
                wr["elapsed_seconds"] = elapsed
                results.append(wr)

        for j, wr in enumerate(wave_results):
            status = "OK" if not isinstance(wr, Exception) and wr.get("success") else "FAIL"
            print(f"    [{bots[j]}]    [{status}] ({elapsed}s)", flush=True)

        # Pause between waves
        if i + wave_size < len(tool_calls):
            print(f"    --- wave pause {wave_pause}s ---", flush=True)
            await asyncio.sleep(wave_pause)

    return results


async def execute_swarm(attack_fn, tool_calls: list[dict]) -> list[dict]:
    """Swarm mode: ALL attacks fire simultaneously. Maximum pressure.

    Args:
        attack_fn: async callable(tool_name, args) -> result dict
        tool_calls: list of {"tool": str, "args": dict}
    """
    bots = [_get_bot_name(i) for i in range(len(tool_calls))]

    print(f"    === SWARM: {len(tool_calls)} bots firing simultaneously ===", flush=True)
    for i, call in enumerate(tool_calls):
        print(f"    [{bots[i]}] -> {call['tool']}", flush=True)

    start = time.time()

    async def _run_bot(idx, call):
        # Random stagger (0-500ms) to simulate real botnet jitter
        await asyncio.sleep(random.uniform(0, 0.5))
        result = await attack_fn(call["tool"], call.get("args", {}))
        result["bot"] = bots[idx]
        return result

    swarm_results = await asyncio.gather(
        *[_run_bot(i, call) for i, call in enumerate(tool_calls)],
        return_exceptions=True,
    )

    elapsed = round(time.time() - start, 1)

    results = []
    for i, sr in enumerate(swarm_results):
        if isinstance(sr, Exception):
            results.append({"bot": bots[i], "error": str(sr), "success": False})
        else:
            sr["elapsed_seconds"] = elapsed
            results.append(sr)

    succeeded = sum(1 for r in results if r.get("success"))
    print(
        f"    === SWARM COMPLETE: {succeeded}/{len(results)} succeeded ({elapsed}s) ===",
        flush=True,
    )
    return results


async def execute_coordinated(attack_fn, phases: list[dict]) -> list[dict]:
    """Coordinated mode: sequential phases, parallel within each phase.

    Args:
        attack_fn: async callable(tool_name, args) -> result dict
        phases: list of {"phase": str, "tools": [str], "description": str}
    """
    all_results = []
    bot_counter = 0

    for phase in phases:
        phase_name = phase.get("phase", "unknown")
        tools = phase.get("tools", [])
        desc = phase.get("description", "")

        if not tools:
            continue

        bots = [_get_bot_name(bot_counter + i) for i in range(len(tools))]
        bot_counter += len(tools)

        print(f"\n    === PHASE: {phase_name} — {desc} ===", flush=True)
        for i, tool in enumerate(tools):
            print(f"    [{bots[i]}] -> {tool}", flush=True)

        start = time.time()

        async def _run_phase_bot(idx, tool_name, bot_name):
            result = await attack_fn(tool_name, {})
            result["bot"] = bot_name
            result["phase"] = phase_name
            return result

        phase_results = await asyncio.gather(
            *[_run_phase_bot(i, tool, bots[i]) for i, tool in enumerate(tools)],
            return_exceptions=True,
        )

        elapsed = round(time.time() - start, 1)

        for i, pr in enumerate(phase_results):
            if isinstance(pr, Exception):
                all_results.append({
                    "bot": bots[i], "phase": phase_name,
                    "error": str(pr), "success": False,
                })
                print(f"    [{bots[i]}]    [FAIL] {pr}", flush=True)
            else:
                pr["elapsed_seconds"] = elapsed
                all_results.append(pr)
                status = "OK" if pr.get("success") else "FAIL"
                desc_short = pr.get("description", "")[:50]
                print(f"    [{bots[i]}]    [{status}] {desc_short}", flush=True)

        # Brief pause between phases
        if phase != phases[-1]:
            await asyncio.sleep(1)

    return all_results


# ================================================================
# BOTNET ORCHESTRATOR
# ================================================================

async def run_botnet(attack_fn, tool_calls: list[dict], mode: str = "sequential",
                     kill_chain_phases: list[dict] | None = None,
                     wave_size: int = 3) -> list[dict]:
    """Main entry point for botnet execution.

    Args:
        attack_fn: async callable(tool_name, args) -> result dict
        tool_calls: flat list of {"tool": str, "args": dict} (for non-coordinated modes)
        mode: "sequential", "wave", "swarm", or "coordinated"
        kill_chain_phases: phase list for coordinated mode
        wave_size: attacks per wave in wave mode
    """
    print(f"\n  [BOTNET] Mode: {mode.upper()} | Attacks: {len(tool_calls) if tool_calls else 'phases'}", flush=True)
    print(f"  [BOTNET] Timestamp: {datetime.now().isoformat()}", flush=True)

    start = time.time()

    if mode == "swarm":
        results = await execute_swarm(attack_fn, tool_calls)
    elif mode == "wave":
        results = await execute_wave(attack_fn, tool_calls, wave_size=wave_size)
    elif mode == "coordinated" and kill_chain_phases:
        results = await execute_coordinated(attack_fn, kill_chain_phases)
    else:
        results = await execute_sequential(attack_fn, tool_calls)

    total_time = round(time.time() - start, 1)
    succeeded = sum(1 for r in results if r.get("success"))

    print(f"\n  [BOTNET] Complete: {succeeded}/{len(results)} succeeded in {total_time}s", flush=True)

    return results
