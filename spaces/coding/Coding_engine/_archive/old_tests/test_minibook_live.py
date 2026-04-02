"""Test Minibook API directly with aiohttp (no relative imports)."""
import asyncio
import aiohttp

MINIBOOK_URL = "http://localhost:8080"

async def test():
    async with aiohttp.ClientSession() as session:
        # 1. Health
        async with session.get(f"{MINIBOOK_URL}/health") as r:
            data = await r.json()
            print(f"1. Health: {data}")

        # 2. Register agents
        agents = {}
        for name in ["CE_Builder", "CE_Fixer", "CE_TreeQuestVerification", "CE_ShinkaEvolve"]:
            async with session.post(f"{MINIBOOK_URL}/api/v1/agents", json={"name": name}) as r:
                if r.status == 200:
                    data = await r.json()
                    agents[name] = data
                    print(f"2. Registered: {name} (key={data['api_key'][:12]}...)")
                else:
                    text = await r.text()
                    print(f"2. Failed {name}: {r.status} {text[:100]}")

        if not agents:
            print("No agents registered, aborting")
            return

        lead = list(agents.values())[0]
        headers = {"Authorization": f"Bearer {lead['api_key']}"}

        # 3. Create project
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects",
            json={"name": "WhatsApp-Service-Pipeline", "description": "Autonomous code gen for WhatsApp service"},
            headers=headers,
        ) as r:
            project = await r.json()
            print(f"3. Project: {project['name']} (id={project['id'][:8]}...)")

        pid = project["id"]

        # 4. Join all agents
        for name, agent in agents.items():
            h = {"Authorization": f"Bearer {agent['api_key']}"}
            async with session.post(f"{MINIBOOK_URL}/api/v1/projects/{pid}/join", json={"role": "developer"}, headers=h) as r:
                if r.status == 200:
                    print(f"4. Joined: {name}")

        # 5. Create posts
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts",
            json={
                "title": "Build succeeded",
                "content": "All files compiled successfully. @CE_TreeQuestVerification please verify code against docs.",
                "type": "status_update",
                "tags": ["build", "success"],
            },
            headers=headers,
        ) as r:
            post = await r.json()
            print(f"5. Post: '{post['title']}' (id={post['id'][:8]}...)")

        # 6. TreeQuest verification comment
        tq = agents.get("CE_TreeQuestVerification")
        if tq:
            tq_h = {"Authorization": f"Bearer {tq['api_key']}"}
            async with session.post(
                f"{MINIBOOK_URL}/api/v1/posts/{post['id']}/comments",
                json={"content": "Verification complete. Found 5 inconsistencies:\n- [HIGH] Missing auth in /api/messages\n- [HIGH] User model diverges from data dictionary\n- [MEDIUM] CORS wildcard in production config"},
                headers=tq_h,
            ) as r:
                comment = await r.json()
                print(f"6. Comment by TreeQuest: {comment['id'][:8]}...")

        # 7. ShinkaEvolve response
        se = agents.get("CE_ShinkaEvolve")
        if se:
            se_h = {"Authorization": f"Bearer {se['api_key']}"}
            async with session.post(
                f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts",
                json={
                    "title": "Evolution Results",
                    "content": "Standard fixers exhausted after 3 attempts on auth.ts.\nEvolved solution found in 12 generations.\nScore improved from 0.3 to 0.85.",
                    "type": "discussion",
                    "tags": ["evolution", "shinka"],
                },
                headers=se_h,
            ) as r:
                evo_post = await r.json()
                print(f"7. Evolution post: '{evo_post['title']}' (id={evo_post['id'][:8]}...)")

        # 8. List all posts
        async with session.get(f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts") as r:
            posts = await r.json()
            print(f"8. Total posts in project: {len(posts)}")
            for p in posts:
                print(f"   - [{p['type']}] {p['title']} by {p.get('author', {}).get('name', '?')}")

        # 9. Check notifications
        for name, agent in agents.items():
            h = {"Authorization": f"Bearer {agent['api_key']}"}
            async with session.get(f"{MINIBOOK_URL}/api/v1/notifications?unread_only=true", headers=h) as r:
                notifs = await r.json()
                if notifs:
                    print(f"9. Notifications for {name}: {len(notifs)}")

    print("\n=== MINIBOOK LIVE TEST PASSED ===")

asyncio.run(test())
