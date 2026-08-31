"""Quick standalone security audit runner."""
import asyncio
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from tools import security_audit


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://goldbach-financial.com"
    print(f"\n  SECURITY AUDIT: {url}\n")

    result = await security_audit(url)

    print(f"  SCORE: {result['score']} / 100\n")

    print("  ISSUES:")
    for issue in result["issues"]:
        sev = issue["severity"]
        marker = {"CRITICAL": "!!!", "HIGH": "!! ", "MEDIUM": " ! ", "LOW": " . ", "INFO": " i "}
        print(f"    [{marker.get(sev, '   ')}] {sev:>8}  {issue['title']}")
        print(f"              {issue['description'][:100]}")
        if issue.get("nginx_fix"):
            print(f"              FIX (nginx): {issue['nginx_fix']}")
        if issue.get("apache_fix"):
            print(f"              FIX (apache): {issue['apache_fix']}")
        print()

    if result.get("cookie_issues"):
        print("  COOKIE ISSUES:")
        for ci in result["cookie_issues"]:
            print(f"    Cookie '{ci['cookie']}': {', '.join(ci['issues'])}")
        print()

    if result.get("recommendations"):
        print("  RECOMMENDATIONS:")
        for rec in result["recommendations"]:
            print(f"    - {rec.get('header', '')}: {rec['description']}")
            if rec.get("nginx_fix"):
                print(f"      nginx: {rec['nginx_fix']}")
        print()

    if result.get("nginx_config_snippet"):
        print("  " + "=" * 56)
        print("  COPY-PASTE NGINX CONFIG:")
        print("  " + "=" * 56)
        print(result["nginx_config_snippet"])
        print()

    if result.get("apache_config_snippet"):
        print("  " + "=" * 56)
        print("  COPY-PASTE APACHE CONFIG:")
        print("  " + "=" * 56)
        print(result["apache_config_snippet"])
        print()


if __name__ == "__main__":
    asyncio.run(main())
