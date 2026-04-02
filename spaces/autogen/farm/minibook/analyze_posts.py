import json, urllib.request
url = "http://localhost:3456/api/v1/projects/2f7f70a3-f0be-4bcc-88a9-daa8230e206d/posts"
posts = json.loads(urllib.request.urlopen(url).read())
types = {}
authors = {}
for p in posts:
    t = p.get("type","?")
    a = p.get("author_name","?")
    types[t] = types.get(t,0) + 1
    authors[a] = authors.get(a,0) + 1
print("=== Posts by Type ===")
for k,v in sorted(types.items(), key=lambda x:-x[1]):
    print(f"  {k:15s} {v}")
print()
print("=== Posts by Author ===")
for k,v in sorted(authors.items(), key=lambda x:-x[1]):
    print(f"  {k:25s} {v}")
print()
print("=== Recent 25 Posts ===")
for p in posts[:25]:
    print(f"  [{p.get('type','?'):10s}] {p.get('author_name','?'):22s} {p.get('title','?')[:55]}")
