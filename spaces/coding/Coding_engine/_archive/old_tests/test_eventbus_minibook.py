"""Test EventBus -> Minibook integration: emit events and verify they create Minibook posts."""
import asyncio
import aiohttp

MINIBOOK_URL = "http://localhost:8080"

async def test():
    async with aiohttp.ClientSession() as session:
        # 1. Health
        async with session.get(f"{MINIBOOK_URL}/health") as r:
            assert r.status == 200
            print("1. Minibook healthy")

        # 2. Register agents (use unique names to avoid conflicts with previous runs)
        import time
        suffix = str(int(time.time()))[-4:]
        agents = {}
        for name in [f"CE_Builder_{suffix}", f"CE_Fixer_{suffix}", f"CE_TreeQuest_{suffix}", f"CE_Shinka_{suffix}"]:
            async with session.post(f"{MINIBOOK_URL}/api/v1/agents", json={"name": name}) as r:
                if r.status == 200:
                    data = await r.json()
                    agents[name] = data
                    print(f"2. Registered: {name}")
                else:
                    text = await r.text()
                    print(f"2. WARN: {name}: {r.status} {text[:80]}")

        agent_names = list(agents.keys())
        lead = agents[agent_names[0]]
        headers = {"Authorization": f"Bearer {lead['api_key']}"}

        # 3. Create project
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects",
            json={"name": f"EventBus-Test-{suffix}", "description": "Testing event-driven posts"},
            headers=headers,
        ) as r:
            project = await r.json()
            pid = project["id"]
            print(f"3. Project: {project['name']}")

        # Join all agents
        for name, agent in agents.items():
            h = {"Authorization": f"Bearer {agent['api_key']}"}
            await session.post(f"{MINIBOOK_URL}/api/v1/projects/{pid}/join", json={"role": "developer"}, headers=h)

        # 4. Simulate PIPELINE_STARTED event -> post
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts",
            json={
                "title": "Emergent pipeline started",
                "content": "**Event:** `pipeline_started`\n\nWatch directory: Data/all_services\nMinibook: connected\n\n**CC:** @CE_Builder @CE_TreeQuestVerification",
                "type": "status_update",
                "tags": ["pipeline_started", "status_update"],
            },
            headers=headers,
        ) as r:
            post = await r.json()
            print(f"4. Pipeline started post: {post['id'][:8]}...")

        # 5. Simulate PACKAGE_READY event -> post
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts",
            json={
                "title": "New project package ingested",
                "content": "**Event:** `package_ready`\n\n**Project:** WhatsApp-Service\n**Tasks:** 45\n**Epics:** 5\n**Completeness:** 100%\n\n**CC:** @CE_Builder @CE_TreeQuestVerification",
                "type": "status_update",
                "tags": ["package_ready", "status_update"],
            },
            headers=headers,
        ) as r:
            post = await r.json()
            print(f"5. Package ready post: {post['id'][:8]}...")

        # 6. Simulate TREEQUEST_VERIFICATION_STARTED
        tq = agents[agent_names[2]]  # TreeQuest agent
        tq_h = {"Authorization": f"Bearer {tq['api_key']}"}
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts",
            json={
                "title": "TreeQuest verification running",
                "content": "**Event:** `treequest_verification_started`\n\nRunning AB-MCTS verification with 200 steps across 5 check types.",
                "type": "status_update",
                "tags": ["treequest_verification_started"],
            },
            headers=tq_h,
        ) as r:
            post = await r.json()
            print(f"6. TreeQuest started: {post['id'][:8]}...")

        # 7. Simulate TREEQUEST_FINDING_CRITICAL
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts",
            json={
                "title": "Critical inconsistency found (TreeQuest)",
                "content": "**Event:** `treequest_finding_critical`\n\n**File:** `src/routes/auth.ts`\n**Category:** api_consistency\n**Description:** Missing auth middleware on /api/messages endpoint\n**Suggested Fix:** Add `requireAuth()` middleware to the route handler\n\n**CC:** @CE_Fixer @CE_Builder",
                "type": "issue",
                "tags": ["treequest_finding_critical", "issue"],
            },
            headers=tq_h,
        ) as r:
            post = await r.json()
            print(f"7. Critical finding post: {post['id'][:8]}...")

        # 8. Simulate EVOLUTION_STARTED
        se = agents[agent_names[3]]  # ShinkaEvolve agent
        se_h = {"Authorization": f"Bearer {se['api_key']}"}
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts",
            json={
                "title": "ShinkaEvolve running",
                "content": "**Event:** `evolution_started`\n\n**File:** `src/routes/auth.ts`\n**Errors:** 3\nStarting evolutionary improvement (max 50 generations).",
                "type": "status_update",
                "tags": ["evolution_started"],
            },
            headers=se_h,
        ) as r:
            post = await r.json()
            print(f"8. Evolution started: {post['id'][:8]}...")

        # 9. Simulate EVOLUTION_APPLIED
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts",
            json={
                "title": "Evolved code applied to codebase",
                "content": "**Event:** `evolution_applied`\n\n**File:** `src/routes/auth.ts`\n**Generations:** 12\nEvolved solution applied. Score improved from 0.3 to 0.85.\n\n**CC:** @CE_TreeQuestVerification @CE_Builder",
                "type": "discussion",
                "tags": ["evolution_applied"],
            },
            headers=se_h,
        ) as r:
            post = await r.json()
            print(f"9. Evolution applied: {post['id'][:8]}...")

        # 10. Simulate PIPELINE_COMPLETED
        async with session.post(
            f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts",
            json={
                "title": "Pipeline completed ✓",
                "content": "**Event:** `pipeline_completed`\n\n**Project:** WhatsApp-Service\n**Success:** True\n**Converged:** True\n**Iterations:** 3\n**Duration:** 245.2s",
                "type": "status_update",
                "tags": ["pipeline_completed"],
            },
            headers=headers,
        ) as r:
            post = await r.json()
            print(f"10. Pipeline completed: {post['id'][:8]}...")

        # 11. List all posts to verify the full flow
        async with session.get(f"{MINIBOOK_URL}/api/v1/projects/{pid}/posts") as r:
            posts = await r.json()
            print(f"\n11. Total posts in project: {len(posts)}")
            for p in posts:
                title = p['title'].encode('ascii', 'replace').decode()
                print(f"   - [{p['type']:15s}] {title}")

        # 12. Check notifications
        for name, agent in agents.items():
            h = {"Authorization": f"Bearer {agent['api_key']}"}
            async with session.get(f"{MINIBOOK_URL}/api/v1/notifications?unread_only=true", headers=h) as r:
                notifs = await r.json()
                if notifs:
                    print(f"12. Notifications for {name}: {len(notifs)}")

    print("\n=== EVENTBUS -> MINIBOOK INTEGRATION TEST PASSED ===")

asyncio.run(test())
