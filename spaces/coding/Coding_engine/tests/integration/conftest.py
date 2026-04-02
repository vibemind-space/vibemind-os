"""
Pytest configuration for integration tests.

Handles Windows-specific encoding issues with emoji characters.
"""
import os
import sys

# Force UTF-8 encoding on Windows
if sys.platform == 'win32':
    # Set environment variable for Python
    os.environ['PYTHONIOENCODING'] = 'utf-8'

    # Try to set console output encoding
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')
    except Exception:
        pass

# Disable colorama's emoji handling issues
os.environ['NO_COLOR'] = '1'


def pytest_configure(config):
    """Configure pytest for integration tests."""
    # Register custom markers
    config.addinivalue_line(
        "markers", "timeout(seconds): mark test with a timeout"
    )
