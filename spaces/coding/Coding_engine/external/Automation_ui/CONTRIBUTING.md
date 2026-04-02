# Contributing to Automation UI

Thank you for your interest in contributing! This guide will help you get started.

## Getting Started

### Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.9+ with pip
- **Git**
- **Windows 10/11** (for desktop automation features)

### Setup

1. Fork and clone the repository
2. Copy environment files:
   ```bash
   cp .env.example .env
   cp moire_tracker/.env.example moire_tracker/.env
   ```
3. Fill in your API keys in `.env`
4. Install dependencies:
   ```bash
   npm install
   cd backend && pip install -r requirements.txt
   ```
5. Start all services:
   ```bash
   scripts\start-all.bat
   ```

## Development Workflow

### Branch Naming

- `feature/short-description` for new features
- `fix/short-description` for bug fixes
- `docs/short-description` for documentation
- `refactor/short-description` for refactoring

### Making Changes

1. Create a feature branch from `main`
2. Make your changes with clear, focused commits
3. Run linting: `npm run lint`
4. Run tests: `npx playwright test`
5. Push and open a Pull Request

### Commit Messages

Use conventional commit style:

```
feat: add desktop streaming reconnect logic
fix: resolve WebSocket timeout on slow connections
docs: update API endpoint documentation
refactor: simplify OCR service initialization
```

### Pull Request Guidelines

- Keep PRs focused on a single change
- Include a description of what changed and why
- Link related issues
- Ensure all CI checks pass

## Code Style

### Frontend (TypeScript/React)

- Use TypeScript strict mode
- Follow existing patterns in `src/components/`
- Use shadcn/ui components from `src/components/ui/`
- Import paths use `@/` alias

### Backend (Python/FastAPI)

- Follow PEP 8
- Use type hints
- Add Pydantic schemas for request/response models
- Register new routers in `backend/app/main.py`

## Reporting Issues

- Use GitHub Issues
- Include steps to reproduce
- Include error messages and logs
- Mention your OS and Node/Python versions

## Security

If you discover a security vulnerability, please see [SECURITY.md](SECURITY.md) for responsible disclosure instructions. **Do not open a public issue for security vulnerabilities.**

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
