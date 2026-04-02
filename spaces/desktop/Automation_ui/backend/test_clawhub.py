"""Quick integration test for ClawHub.ai backend."""
import asyncio
import sys
sys.path.insert(0, '.')


async def test():
    passed = 0

    # Test 1: Skill Models
    from app.models.skill import SkillSummary, SkillCategory
    s = SkillSummary(id='test', name='Test', description='desc', version='1.0', author='me', category=SkillCategory.AUTOMATION, install_count=0, rating=4.5)
    print(f'[OK] 1. Models: {s.name} ({s.category})')
    passed += 1

    # Test 2: Mock ClawHub Client - Search
    from app.services.clawhub_client import get_clawhub_client
    client = get_clawhub_client(use_live=False)
    result = await client.search_skills('browser')
    print(f'[OK] 2. Search "browser": {result.total} results -> {[s.name for s in result.skills]}')
    passed += 1

    # Test 3: Search all
    result_all = await client.search_skills('')
    print(f'[OK] 3. Search all: {result_all.total} skills')
    passed += 1

    # Test 4: Get skill detail
    detail = await client.get_skill('github-manager')
    print(f'[OK] 4. Detail: {detail.name} v{detail.version}, permissions={[p.value for p in detail.permissions]}')
    passed += 1

    # Test 5: Trending
    trending = await client.get_trending(5)
    print(f'[OK] 5. Trending top 5: {[s.name for s in trending]}')
    passed += 1

    # Test 6: Categories
    cats = await client.get_categories()
    print(f'[OK] 6. Categories: {cats}')
    passed += 1

    # Test 7: Skill Manager - Install
    from app.services.skill_manager import get_skill_manager
    manager = get_skill_manager()
    installed = await manager.install_skill(detail)
    print(f'[OK] 7. Installed: {installed.name} at {installed.local_path}')
    passed += 1

    # Test 8: List installed
    all_installed = manager.list_installed()
    print(f'[OK] 8. Installed count: {len(all_installed)}')
    assert len(all_installed) == 1
    passed += 1

    # Test 9: Execute skill
    exec_result = await manager.execute_skill('github-manager', {'command': 'list repos'})
    print(f'[OK] 9. Execute: success={exec_result.success}, time={exec_result.execution_time_ms:.1f}ms')
    assert exec_result.success
    passed += 1

    # Test 10: Toggle off
    toggled = await manager.toggle_skill('github-manager', False)
    print(f'[OK] 10. Toggle off: enabled={toggled.enabled}')
    assert not toggled.enabled
    passed += 1

    # Test 11: Execute disabled
    exec_disabled = await manager.execute_skill('github-manager', {})
    print(f'[OK] 11. Execute disabled: success={exec_disabled.success}, error={exec_disabled.error}')
    assert not exec_disabled.success
    passed += 1

    # Test 12: Toggle back on + stats
    await manager.toggle_skill('github-manager', True)
    stats = manager.get_stats()
    print(f'[OK] 12. Stats: installed={stats["total_installed"]}, executions={stats["total_executions"]}')
    passed += 1

    # Test 13: Uninstall
    ok = await manager.uninstall_skill('github-manager')
    remaining = manager.list_installed()
    print(f'[OK] 13. Uninstall: success={ok}, remaining={len(remaining)}')
    assert ok and len(remaining) == 0
    passed += 1

    # Test 14: Search with category filter
    result_dev = await client.search_skills('', category=SkillCategory.DEVELOPMENT)
    print(f'[OK] 14. Category filter (development): {[s.name for s in result_dev.skills]}')
    passed += 1

    # Test 15: Non-existent skill
    none_skill = await client.get_skill('does-not-exist')
    print(f'[OK] 15. Non-existent skill: {none_skill}')
    assert none_skill is None
    passed += 1

    print(f'\n=== ALL {passed}/15 TESTS PASSED ===')


if __name__ == '__main__':
    asyncio.run(test())
