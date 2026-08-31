"""Check if site reflects user input (potential XSS vectors)."""
import asyncio
import urllib.request
import urllib.error
import urllib.parse
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


CANARY = "XSSCANARY7391"

TEST_VECTORS = [
    ("Search parameter ?s=", "/?s=" + CANARY),
    ("Search parameter ?q=", "/?q=" + CANARY),
    ("Search parameter ?search=", "/?search=" + CANARY),
    ("Page parameter ?p=", "/?p=" + CANARY),
    ("WordPress search", "/?" + urllib.parse.urlencode({"s": CANARY})),
    ("404 page reflection", "/" + CANARY),
]


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://goldbach-financial.com"
    print(f"\n  XSS REFLECTION CHECK: {url}\n")

    for name, path in TEST_VECTORS:
        test_url = url.rstrip("/") + path
        try:
            req = urllib.request.Request(test_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            })
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda u=test_url: urllib.request.urlopen(
                    urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}),
                    timeout=10,
                )
            )
            body = resp.read().decode("utf-8", errors="replace")

            if CANARY in body:
                # Check context: is it inside a tag, attribute, or plain text?
                # Find surrounding context
                idx = body.index(CANARY)
                context = body[max(0, idx-80):idx+len(CANARY)+80]

                in_tag = bool(re.search(r'<[^>]*' + CANARY, context))
                in_attr = bool(re.search(r'(value|content|alt|title)=["\'][^"\']*' + CANARY, context))
                in_script = "<script" in body[max(0, idx-200):idx].lower()

                context_type = "plain text"
                if in_script:
                    context_type = "INSIDE SCRIPT TAG (!)"
                elif in_attr:
                    context_type = "inside HTML attribute"
                elif in_tag:
                    context_type = "inside HTML tag"

                print(f"  [REFLECTED] {name}")
                print(f"              URL: {test_url}")
                print(f"              Context: {context_type}")
                print(f"              Surrounding: ...{context.strip()[:120]}...")
                print()
            else:
                print(f"  [safe]      {name} - not reflected")

        except urllib.error.HTTPError as e:
            print(f"  [safe]      {name} - HTTP {e.code}")
        except Exception as e:
            print(f"  [error]     {name} - {e}")

    # Also check forms on the page
    print(f"\n  FORM ANALYSIS:")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=10)
        )
        html = resp.read().decode("utf-8", errors="replace")

        forms = re.findall(r'<form[^>]*>(.*?)</form>', html, re.IGNORECASE | re.DOTALL)
        print(f"  Found {len(forms)} form(s) on main page\n")

        for i, form in enumerate(forms):
            inputs = re.findall(r'<input[^>]+>', form, re.IGNORECASE)
            textareas = re.findall(r'<textarea[^>]*>', form, re.IGNORECASE)

            action_match = re.search(r'action=["\']([^"\']*)["\']', form, re.IGNORECASE)
            action = action_match.group(1) if action_match else "(self)"

            method_match = re.search(r'method=["\']([^"\']*)["\']', form, re.IGNORECASE)
            method = method_match.group(1).upper() if method_match else "GET"

            print(f"  Form #{i+1}: {method} → {action}")
            print(f"    Inputs: {len(inputs)}, Textareas: {len(textareas)}")

            for inp in inputs:
                type_match = re.search(r'type=["\']([^"\']*)["\']', inp, re.IGNORECASE)
                name_match = re.search(r'name=["\']([^"\']*)["\']', inp, re.IGNORECASE)
                inp_type = type_match.group(1) if type_match else "text"
                inp_name = name_match.group(1) if name_match else "?"

                if inp_type.lower() in ("text", "search", "email", "url", "tel"):
                    print(f"    → Input '{inp_name}' (type={inp_type}) - potential XSS vector")

    except Exception as e:
        print(f"  Error: {e}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
