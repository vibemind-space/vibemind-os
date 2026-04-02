import sys
sys.path.insert(0, '.')
from minibook.swarm.knowledge import GENERIC_MAIN_PY
from minibook.swarm.pipeline import _fix_truncated_tools_py
from minibook.swarm.docker_ops import docker_build_test, docker_run_test, docker_run_test_with_args
from minibook.swarm.llm import call_gpt4o_json
print('All imports OK')
print('GENERIC_MAIN_PY:', len(GENERIC_MAIN_PY), 'chars')
