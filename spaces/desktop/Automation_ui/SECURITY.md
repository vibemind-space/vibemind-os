# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public GitHub issue**
2. Email your findings to the maintainers (see repository contact info)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to provide a fix within 7 days for critical issues.

## Security Best Practices for Contributors

- Never commit secrets, API keys, or credentials to the repository
- Use `.env` files for all sensitive configuration (see `.env.example`)
- All `.env` files are gitignored by default
- Review the [CONTRIBUTING.md](CONTRIBUTING.md) guide before submitting code

## Known Security Considerations

- This project uses desktop automation capabilities (screen capture, mouse/keyboard control). Only run it in trusted environments.
- API keys for LLM services (OpenRouter, etc.) should be kept confidential and rotated regularly.
- The WebSocket streaming feature transmits screen content. Use it only on trusted networks.
