#!/usr/bin/env python3
"""Test imports for new modules."""
import sys
sys.path.insert(0, '.')

# Test scaffolding directly (bypassing __init__.py)
import importlib.util
spec = importlib.util.spec_from_file_location("project_initializer", "src/scaffolding/project_initializer.py")
project_initializer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project_initializer)
ProjectInitializer = project_initializer.ProjectInitializer
ProjectType = project_initializer.ProjectType
print('Scaffolding: OK')

# Test completeness checker directly (bypassing __init__.py to avoid circular imports)
spec2 = importlib.util.spec_from_file_location("completeness_checker", "src/tools/completeness_checker.py")
completeness_checker = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(completeness_checker)
CompletenessChecker = completeness_checker.CompletenessChecker
print('Completeness Checker: OK')

# Test convergence
from src.mind.convergence import AUTONOMOUS_CRITERIA
print('AUTONOMOUS_CRITERIA: OK')
print(f'  max_iterations={AUTONOMOUS_CRITERIA.max_iterations}')
print(f'  max_time={AUTONOMOUS_CRITERIA.max_time_seconds}s')
print(f'  require_all_tests_pass={AUTONOMOUS_CRITERIA.require_all_tests_pass}')

print('\nAll new modules imported successfully!')
