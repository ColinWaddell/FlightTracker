# Security Policy

## Reporting a Vulnerability

If you discover a security issue in FlightTracker, please report it responsibly
rather than opening a public GitHub issue.

**Email:** security@colinwaddell.com

Include as much detail as you can — steps to reproduce, affected versions, and
any potential impact. I'll acknowledge receipt within 48 hours and aim to
provide a fix or mitigation as soon as reasonably possible.

## Sharing Config Safely

If a security issue involves your configuration, **do not paste your raw
`config.json`** — it may contain API keys and password hashes.

Use the **"Download debug config"** button in the footer of the Settings page
in the web UI. This exports your configuration with all sensitive fields
automatically replaced with `***REDACTED***`, making it safe to share.