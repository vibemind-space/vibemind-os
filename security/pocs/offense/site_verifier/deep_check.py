"""Quick deep check: ports + subdomains + paths for a domain."""
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from tools import port_scan, subdomain_enum, path_discovery, robots_sitemap_scan


async def main():
    domain = sys.argv[1] if len(sys.argv) > 1 else "goldbach-financial.com"
    url = f"https://{domain}"
    print(f"\n  DEEP CHECK: {domain}\n")

    ps, sd, paths, robots = await asyncio.gather(
        port_scan(domain),
        subdomain_enum(domain),
        path_discovery(url),
        robots_sitemap_scan(url),
    )

    print("=" * 60)
    print("  OPEN PORTS")
    print("=" * 60)
    for p in ps["open_ports"]:
        banner = (p.get("banner") or "")[:80]
        sev = p.get("severity", "?")
        print(f"  [{sev:>8}]  Port {p['port']:>5}  {p['service']:<16}  Banner: {banner or '-'}")

    print(f"\n  Total: {len(ps['open_ports'])} open / {ps['total_scanned']} scanned\n")

    print("=" * 60)
    print("  SUBDOMAINS")
    print("=" * 60)
    for s in sd["found_subdomains"]:
        flag = "  << RISKY" if s["risky"] else ""
        print(f"  {s['subdomain']:<40}  {s['ip']}{flag}")

    print(f"\n  Total: {sd['total_found']} found / {sd['total_checked']} checked\n")

    print("=" * 60)
    print("  EXPOSED PATHS")
    print("=" * 60)
    for p in paths["found_paths"]:
        print(f"  [{p['severity']:>8}]  HTTP {p['status']}  {p['path']}")
        print(f"             {p['description']}")

    print(f"\n  Total: {len(paths['found_paths'])} found / {paths['checked_count']} checked\n")

    print("=" * 60)
    print("  ROBOTS.TXT")
    print("=" * 60)
    if robots["robots_txt"]["found"]:
        print("  Disallowed paths:")
        for p in robots["robots_txt"]["disallowed_paths"]:
            print(f"    {p}")
        if robots["exposed_sensitive_paths"]:
            print("\n  Sensitive paths exposed:")
            for p in robots["exposed_sensitive_paths"]:
                print(f"    [{p['source']}] {p['path']}")
                print(f"      {p['concern']}")
    else:
        print("  No robots.txt found")

    print()


if __name__ == "__main__":
    asyncio.run(main())
