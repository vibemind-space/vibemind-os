"""
Log Analyzer - Windows Event Log Security Analysis
=====================================================
Parses Windows Event Logs and uses LLM to detect attack patterns.

Nutzung:
  python main.py --scan                    # Letzte 24h analysieren
  python main.py --scan --hours 72         # Letzte 72h
  python main.py --brute-force             # Nur Brute-Force Check
  python main.py --timeline --hours 48     # Timeline der letzten 48h
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

from tools import (
    parse_security_log, parse_system_log,
    detect_brute_force, detect_priv_escalation,
    detect_new_services, build_timeline,
)


async def main():
    parser = argparse.ArgumentParser(description="Windows Event Log Security Analyzer")
    parser.add_argument("--scan", action="store_true", help="Full log analysis")
    parser.add_argument("--brute-force", action="store_true", help="Brute-force detection only")
    parser.add_argument("--timeline", action="store_true", help="Build event timeline")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back")
    args = parser.parse_args()

    if not any([args.scan, args.brute_force, args.timeline]):
        parser.print_help()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  LOG ANALYZER")
    print("  Windows Event Log Security Analysis")
    print("=" * 60)
    print(f"\n  Timeframe: last {args.hours} hours")
    print(f"  Date: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")

    if args.scan:
        print("  [1/5] Parsing Security Log...", flush=True)
        sec = await parse_security_log(hours=args.hours)
        print(f"         {sec['total_events']} events | Counts: {sec['event_counts']}")

        print("  [2/5] Parsing System Log...", flush=True)
        sys_log = await parse_system_log(hours=args.hours)
        print(f"         {sys_log['total_events']} events | New services: {len(sys_log['new_services'])}")

        print("  [3/5] Detecting Brute-Force...", flush=True)
        bf = await detect_brute_force(hours=args.hours)
        print(f"         Failed logins: {bf['total_failed_logins']} | Brute-force: {'YES' if bf['brute_force_detected'] else 'no'}")

        print("  [4/5] Detecting Privilege Escalation...", flush=True)
        pe = await detect_priv_escalation(hours=args.hours)
        print(f"         Admin logins: {len(pe['admin_logins'])} | Suspicious: {len(pe['suspicious'])}")

        print("  [5/5] Detecting New Services...", flush=True)
        ns = await detect_new_services(hours=args.hours)
        print(f"         New: {len(ns['new_services'])} | Suspicious: {len(ns['suspicious_services'])}")

        # Collect all issues
        all_issues = []
        for result in [bf, pe, ns]:
            all_issues.extend(result.get("issues", []))

        print(f"\n  {'=' * 56}")
        print(f"  FINDINGS: {len(all_issues)}")
        print(f"  {'=' * 56}")
        for issue in all_issues:
            print(f"  [{issue['severity']:>8}] {issue['title']}")
            print(f"            {issue['description'][:100]}")
        if not all_issues:
            print("  No security issues detected.")
        print()

    elif args.brute_force:
        print("  Detecting Brute-Force...", flush=True)
        bf = await detect_brute_force(hours=args.hours)
        print(f"\n  Failed logins: {bf['total_failed_logins']}")
        print(f"  Brute-force detected: {'YES' if bf['brute_force_detected'] else 'no'}")
        for src in bf.get("attack_sources", []):
            print(f"    Source: {src['source']} | Attempts: {src['attempt_count']} | Targets: {', '.join(src['target_users'][:3])}")

    elif args.timeline:
        print("  Building timeline...", flush=True)
        tl = await build_timeline(hours=args.hours)
        print(f"\n  Total events: {tl['total_events']}\n")
        for event in tl["timeline"][:50]:
            time_short = event["time"][:19] if event["time"] else "?"
            print(f"  {time_short}  [{event['source']:>8}]  {event['event_id']}  {event['label']:<25}  {event.get('user', '')}")


if __name__ == "__main__":
    asyncio.run(main())
