"""Test Groq with a large prompt (simulating 12K token classifier prompt)."""
import os
import json
import urllib.request

GROQ_KEY = os.environ.get("GROQ_API_KEY") or open("C:/Users/User/Desktop/poc_injection_chain/.env").read().split("GROQ_API_KEY=")[1].split("\n")[0].strip()

# ~12K tokens
big_system = "You are an intent classifier. " * 1500
data = json.dumps({
    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
    "messages": [
        {"role": "system", "content": big_system},
        {"role": "user", "content": "Zeig meine Spaces"},
    ],
    "max_tokens": 100,
}).encode()

req = urllib.request.Request(
    "https://api.groq.com/openai/v1/chat/completions",
    data=data,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_KEY}"},
)

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
        print(f"OK: {result['choices'][0]['message']['content'][:100]}")
        print(f"Tokens: {result.get('usage', {})}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"FAIL ({e.code}): {body[:300]}")
