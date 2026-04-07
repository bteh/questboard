# Security Policy

## Reporting a vulnerability

Do not open public GitHub issues for security-sensitive problems.

Instead:

1. Email the maintainer or repository owner directly through the contact information available on GitHub.
2. Include a clear description, reproduction steps, affected files or routes, and any relevant logs or screenshots.
3. If secrets may be exposed, rotate them immediately before sending the report.

## What to report

Please report issues such as:

- authentication or authorization bypasses
- cross-workspace or cross-user data leaks
- insecure handling of API keys or tokens
- arbitrary file access, SSRF, command execution, or injection bugs
- resume or job data exposure
- dependency vulnerabilities with a realistic impact on Launchboard

## What not to report publicly

- live API keys, tokens, cookies, or personal data
- exploit details before maintainers have time to assess and patch

## Scope notes

Launchboard integrates with third-party job sources and AI providers. Some upstream scraping, rate limiting, or provider-policy issues may be product risks without being security vulnerabilities. When in doubt, report privately and include why you think the issue is security-relevant.

## Response goals

Maintainers will try to:

- acknowledge receipt promptly
- confirm whether the report is in scope
- communicate whether a fix or mitigation is planned

No SLA is promised, but responsible disclosure is appreciated.
