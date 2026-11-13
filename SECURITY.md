# Security Policy

## Supported versions

Only the latest release and `main` get security fixes.

## Reporting a vulnerability

**Please don't open a public issue.** Use GitHub private vulnerability
reporting (Security tab → *Report a vulnerability*), or contact the
maintainer (@ShoelessTim) privately.

Include what's affected, how to reproduce it, and the impact.
You'll get an acknowledgment within a few days.

## What's in place

- CI scans every push and PR for committed secrets (gitleaks).
- CI audits Python dependencies for known vulnerabilities (pip-audit, report only).
- Dependabot alerts and security-fix PRs are on; Actions are kept current monthly.

## If a secret is committed

Rotate it first, then remove it from history.
