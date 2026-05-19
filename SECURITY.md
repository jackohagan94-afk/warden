# Warden — Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | Yes       |
| < 0.3   | No        |

## Reporting a Vulnerability

Report security vulnerabilities by opening a **private** issue or emailing the maintainer directly. Do not open public issues for security concerns.

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive a response within 48 hours.

## Security Practices

- API keys are never logged or printed
- Configuration is loaded via `yaml.safe_load` (no arbitrary code execution)
- All HTTP requests use configurable timeouts
- Container runs as non-root user
- Dependencies are scanned for known vulnerabilities on every release
- Static analysis (bandit) runs on every push to main
