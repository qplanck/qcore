# Security Policy

QCore is early alpha software, but security reports are welcome now.

## Supported Versions

Only the current `main` branch and the latest published alpha are supported.

## Reporting a Vulnerability

Please do not file public issues for suspected vulnerabilities. Email the
maintainers or use GitHub private vulnerability reporting once it is enabled for
the repository.

Include:

- affected version or commit
- reproduction steps
- expected and actual behavior
- any relevant input files, such as OpenQASM documents

## Security Boundaries

- OpenQASM import is data parsing only and must not execute Python.
- QIR export emits text only; callers must validate it before external execution.
- Pulse/calibration contracts validate local data only and never submit hardware
  jobs from the core package.
- Optional framework adapters are trusted local dependencies.
- Future plugins must document trust boundaries before they are enabled by
  default.
