"""Quick check what wp-config.php actually returns."""
import asyncio
import urllib.request


async def main():
    urls = [
        "https://goldbach-financial.com/wp-config.php",
        "https://goldbach-financial.com/wp-login.php",
        "https://goldbach-financial.com/admin",
    ]

    for url in urls:
        print(f"\n{'='*60}")
        print(f"  {url}")
        print(f"{'='*60}")
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Security Audit)"
            })
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda u=url: urllib.request.urlopen(
                    urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}),
                    timeout=10,
                )
            )
            body = resp.read().decode("utf-8", errors="replace")
            print(f"  Status: {resp.status}")
            print(f"  Content-Type: {resp.headers.get('Content-Type')}")
            print(f"  Content-Length: {len(body)} bytes")
            print(f"  First 500 chars:")
            print(f"  {body[:500]}")

            # Check for actual credentials
            danger_keywords = ["DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "AUTH_KEY", "define("]
            found = [kw for kw in danger_keywords if kw in body]
            if found:
                print(f"\n  !!! DANGER: Found credential keywords: {found}")
            else:
                print(f"\n  No credential keywords found in response body.")

        except urllib.error.HTTPError as e:
            print(f"  HTTP Error: {e.code} {e.reason}")
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
