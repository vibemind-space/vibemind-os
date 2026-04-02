import py_compile
import sys

files = [
    'src/mind/event_bus.py',
    'src/services/emergent_pipeline.py',
    'src/services/pipeline_metrics.py',
    'src/services/pipeline_health.py',
    'src/services/minibook_connector.py',
    'src/services/davelovable_bridge.py',
    'src/services/openclaw_bridge.py',
    'src/agents/shinka_evolve_agent.py',
    'src/agents/treequest_verification_agent.py',
]
ok = 0
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f'OK: {f}')
        ok += 1
    except py_compile.PyCompileError as e:
        print(f'FAIL: {f}: {e}')
print(f'\n{ok}/{len(files)} compiled clean')
