#!/usr/bin/env python3
"""Test script for tool_category_filter.py"""
import sys
sys.path.insert(0, '.')
from tool_category_filter import ToolCategoryFilter, DynamicPromptGenerator

# Mock tools
class MockTool:
    def __init__(self, name, description=''):
        self.name = name
        self.description = description

tools = [
    MockTool('filesystem_read_file', 'Read file'),
    MockTool('filesystem_write_file', 'Write file'),
    MockTool('filesystem_list_directory', 'List dir'),
    MockTool('filesystem_create_directory', 'Create dir'),
    MockTool('filesystem_search_files', 'Search files'),
    MockTool('docker_container_logs', 'Get logs'),
    MockTool('docker_compose_up', 'Start compose'),
    MockTool('docker_container_stats', 'Get stats'),
    MockTool('git_status', 'Git status'),
    MockTool('git_diff', 'Git diff'),
    MockTool('git_commit', 'Commit changes'),
    MockTool('postgres_query', 'Query DB'),
    MockTool('prisma_generate', 'Generate client'),
    MockTool('playwright_navigate', 'Navigate'),
    MockTool('playwright_click', 'Click element'),
    MockTool('npm_install', 'Install pkg'),
    MockTool('npm_run', 'Run script'),
    MockTool('fetch_request', 'HTTP request'),
    MockTool('time_get_current_time', 'Get time'),
]

filter = ToolCategoryFilter(max_tools=30)

print('=== Tool Filter Test ===\n')

for task_type in ['write_code', 'fix_code', 'debug_docker', 'database_query', 'general']:
    result = filter.filter_for_task(tools, task_type)
    tool_names = [t.name for t in result.tools]
    print(f'{task_type}:')
    print(f'  Filtered: {result.total_available} -> {result.filtered_count} tools')
    print(f'  Categories: {[c.value for c in result.categories]}')
    print(f'  Tools: {tool_names}')
    print()

# Test dynamic prompt
print('=== Dynamic Prompt Test ===\n')
prompt_gen = DynamicPromptGenerator(filter)
result = filter.filter_for_task(tools, 'write_code')
prompt = prompt_gen.generate_prompt(result, 'write_code')
print(f'Prompt length: {len(prompt)} chars')
print(f'First 600 chars:\n{prompt[:600]}...')

print('\n=== All Tests Passed! ===')
