# Contributing to SoundTouch Open Cloud

Thank you for helping improve this project!

## How to contribute

1. **Fork** the repository and create a branch: `git checkout -b feature/my-feature`
2. Make your changes and write tests where applicable
3. Run linting: `cd apps/backend && ruff check src/`
4. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat: add Spotify search`
   - `fix: preset slot 3 not saving`
   - `docs: update README`
5. Open a **Pull Request** with a clear description

## Reporting bugs

Open a [GitHub Issue](../../issues) with:
- Your device model and firmware version
- Docker version and host OS
- Steps to reproduce
- Relevant log output (`docker compose logs`)

## Requesting features

Open a [Discussion](../../discussions) — this keeps ideas visible to the community before implementation starts.

## Code style

- Python: [Ruff](https://docs.astral.sh/ruff/) (line length 100)
- TypeScript: ESLint + Prettier defaults
- No external secrets or API keys in code
