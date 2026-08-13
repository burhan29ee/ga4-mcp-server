# Security Policy

## Supported versions

This project is pre-1.0; the latest release on `main` is supported.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Instead, use
GitHub's private vulnerability reporting (the "Report a vulnerability" button
under the repository's **Security** tab). We aim to acknowledge reports within a
few days.

## Handling credentials

This server authenticates with a Google Cloud **service-account key** — a
credential that grants access to your Google Analytics data.

- **Never commit the key.** The included `.gitignore` blocks `*.json` (except
  the example config), `.env`, and `*-key.json` / `service-account*.json`, but
  keep your key outside the repository regardless.
- Grant the service account the least access it needs (Viewer/Analyst for
  read-only use, Editor only if you need write access).
- If a key is ever exposed, delete it in Google Cloud
  (IAM & Admin -> Service Accounts -> Keys) and create a new one.
- `send_ga4_event` writes data **into** a property. Use `validate=True` first to
  check payloads without ingesting them.
