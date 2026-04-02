# Contributing to Coding Engine

Thank you for your interest in contributing to Coding Engine! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop
- Git

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/coding-engine.git
   cd coding-engine
   ```
3. Add the upstream remote:
   ```bash
   git remote add upstream https://github.com/ORIGINAL_OWNER/coding-engine.git
   ```

## Development Setup

### Python Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install
```

### Dashboard Development

```bash
cd dashboard-app
npm install
npm run dev  # Web mode
npm run dev:electron  # Electron mode
```

### Environment Configuration

```bash
cp .env.example .env
# Edit .env with your configuration
```

## How to Contribute

### Reporting Bugs

Before creating a bug report:
1. Check existing issues to avoid duplicates
2. Collect information about the bug:
   - Stack trace
   - OS and Python version
   - Steps to reproduce

Create a bug report using our [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).

### Suggesting Features

We welcome feature suggestions! Please:
1. Check existing issues and discussions
2. Describe the problem your feature would solve
3. Explain your proposed solution

Use our [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).

### Contributing Code

1. **Find an issue** - Look for issues labeled `good first issue` or `help wanted`
2. **Discuss** - Comment on the issue to let others know you're working on it
3. **Branch** - Create a feature branch from `main`
4. **Code** - Write your code following our standards
5. **Test** - Add tests for your changes
6. **Document** - Update documentation as needed
7. **Submit** - Open a pull request

## Pull Request Process

### Before Submitting

- [ ] Code follows the project's coding standards
- [ ] All tests pass locally
- [ ] New code has appropriate test coverage
- [ ] Documentation is updated
- [ ] Commit messages are clear and descriptive

### PR Guidelines

1. **Title**: Use a clear, descriptive title
   - `feat: Add new agent for database migrations`
   - `fix: Resolve race condition in EventBus`
   - `docs: Update API documentation`

2. **Description**: Include:
   - Summary of changes
   - Related issue numbers
   - Screenshots for UI changes
   - Breaking changes (if any)

3. **Size**: Keep PRs focused and reasonably sized

### Review Process

1. Maintainers will review your PR
2. Address any requested changes
3. Once approved, a maintainer will merge your PR

## Coding Standards

### Python

- Follow [PEP 8](https://pep8.org/) style guide
- Use type hints for function signatures
- Maximum line length: 100 characters
- Use descriptive variable names

```python
# Good
async def process_event(event: Event, timeout: float = 5.0) -> bool:
    """Process an event and return success status."""
    ...

# Bad
async def proc(e, t=5):
    ...
```

### TypeScript/React

- Use TypeScript strict mode
- Follow React best practices
- Use functional components with hooks
- Prefer named exports

```typescript
// Good
export function ProjectCard({ project }: ProjectCardProps): JSX.Element {
  const [isLoading, setIsLoading] = useState(false);
  ...
}

// Bad
export default function(props) {
  var loading = false;
  ...
}
```

### Git Commits

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: Add new feature
fix: Fix bug
docs: Update documentation
style: Format code (no logic changes)
refactor: Refactor code
test: Add or update tests
chore: Update build scripts, etc.
```

## Testing

### Running Tests

```bash
# Python tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific test file
pytest tests/mind/test_event_bus.py -v

# Dashboard tests
cd dashboard-app
npm test
```

### Writing Tests

- Write tests for new features
- Update tests for bug fixes
- Aim for meaningful coverage, not just high numbers
- Test edge cases and error conditions

```python
# Example test
async def test_event_bus_publishes_to_subscribers():
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(EventType.BUILD_SUCCEEDED, handler)
    await bus.publish(Event(type=EventType.BUILD_SUCCEEDED, data={}))

    assert len(received) == 1
    assert received[0].type == EventType.BUILD_SUCCEEDED
```

## Documentation

### Code Documentation

- Add docstrings to all public functions and classes
- Use Google-style docstrings for Python
- Use JSDoc for TypeScript

```python
def create_agent(name: str, config: AgentConfig) -> AutonomousAgent:
    """Create and configure an autonomous agent.

    Args:
        name: The unique identifier for the agent.
        config: Configuration options for the agent.

    Returns:
        A configured AutonomousAgent instance ready to start.

    Raises:
        ValueError: If the name is already in use.
    """
    ...
```

### Updating Documentation

- Update README.md for user-facing changes
- Update CLAUDE.md for developer-facing changes
- Add inline comments for complex logic

## Agent Development

### Creating a New Agent

1. Extend `AutonomousAgent` base class
2. Define `subscribed_events` property
3. Implement `should_act()` and `act()` methods
4. Register in orchestrator

```python
class MyCustomAgent(AutonomousAgent):
    """Custom agent for specific task."""

    @property
    def subscribed_events(self) -> list[EventType]:
        return [EventType.BUILD_SUCCEEDED]

    async def should_act(self, event: Event) -> bool:
        return event.type in self.subscribed_events

    async def act(self) -> None:
        # Implement agent logic
        ...
```

## Questions?

- Open a [Discussion](https://github.com/yourusername/coding-engine/discussions)
- Check existing issues and documentation
- Join our community chat (coming soon)

Thank you for contributing to Coding Engine!
