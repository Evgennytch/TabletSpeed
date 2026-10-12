# Contributing

Contributions are welcome. Please open an issue for large changes and keep pull requests focused.

- Use Python 3.11 or newer and type hints for core code.
- Keep measurement logic in `src/tabletspeed/metrics.py`, independent from Qt.
- Add tests for measurement and settings changes.
- Run `python -m pytest` before submitting.
- Do not add telemetry, game-process injection, or undocumented game integrations.
