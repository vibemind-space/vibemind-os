#!/usr/bin/env python3
"""Quick test of CLI wrapper."""
import asyncio
from src.autogen.cli_wrapper import ClaudeCLI

async def test():
    cli = ClaudeCLI(working_dir='output')
    result = await cli.execute('Create a simple Python function that prints hello world. Use format: ```python:hello.py')
    print('Success:', result.success)
    print('Files:', len(result.files))
    if result.files:
        for f in result.files:
            print(f'  - {f.path} ({f.language})')
    if result.error:
        print('Error:', result.error[:300])
    print('Output length:', len(result.output))

if __name__ == "__main__":
    asyncio.run(test())
