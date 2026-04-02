import sys, asyncio, tempfile, shutil
from pathlib import Path
sys.path.insert(0, '.')
from minibook.swarm.knowledge import GENERIC_MAIN_PY
from minibook.swarm.docker_ops import docker_build_test, docker_run_test

src = Path('output/core_v57')
build_dir = Path(tempfile.mkdtemp(prefix='rerun_dbg_'))
print(f"Build dir: {build_dir}")

for item in src.iterdir():
    if item.name in ('output', 'output_rerun'):
        continue
    dest = build_dir / item.name
    if item.is_dir():
        shutil.copytree(item, dest)
    else:
        shutil.copy2(item, dest)

(build_dir / 'src' / 'main.py').write_text(GENERIC_MAIN_PY, encoding='utf-8')
(build_dir / 'output').mkdir(exist_ok=True)

async def run():
    print("Building Docker image...")
    b = await docker_build_test(build_dir)
    print(f"Build: {b['status']}")
    if b['status'] != 'PASS':
        print("Build logs:", b.get('output', '')[-2000:])
        return

    print("Running container (30s timeout)...")
    r = await docker_run_test(build_dir, timeout=30)
    print(f"Run: {r['status']} ({r.get('duration', 0):.1f}s)")
    logs = r.get('logs', '')
    print("Container logs:", logs[-3000:])

asyncio.run(run())
