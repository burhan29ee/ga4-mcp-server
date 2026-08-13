# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-13

### Added
- Initial release.
- **Read tools:** account/property discovery, property details, data streams,
  reports (`run_report`), realtime reports, and listing of custom dimensions,
  custom metrics, key events, and audiences.
- **Write tools:** create and archive custom dimensions, create custom metrics,
  create key events (conversions), create and archive audiences, manage
  Measurement Protocol secrets, and send events via the Measurement Protocol.
- Service-account authentication via `GOOGLE_APPLICATION_CREDENTIALS`.
- Packaging as an installable console script (`ga4-mcp-server`).

[0.1.0]: https://github.com/burhan29ee/ga4-mcp-server/releases/tag/v0.1.0
