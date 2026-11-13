# Security

## Reporting a problem

Please don't open a public issue for a security problem. Use GitHub's **Report a vulnerability** button on the [Security tab](https://github.com/ShoelessTim/stick-citizen/security/advisories/new) instead. You'll get a reply within a week.

## What's in scope

- The Stick Citizen app and its installer (latest release).
- Layout and stick-map files it reads, if a crafted file can make it do something harmful.

Stick Citizen runs locally, reads your stick input and Star Citizen's bindings files, and writes only to `%APPDATA%\StickCitizen` and the layout files you save. It makes no network connections.

## Supported versions

Only the latest release gets fixes.
