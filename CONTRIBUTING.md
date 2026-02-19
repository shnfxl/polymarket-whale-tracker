# Contributing

## Development Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run Locally
```bash
python3 -m whale_tracker --once --dry-run
```

## Tests
```bash
python3 -m unittest discover -s tests -v
```

## Pull Request Guidelines
- Keep changes focused and small.
- Include tests for behavior changes.
- Update `README.md` and `.env.example` when config/runtime behavior changes.
- Do not commit secrets (`.env`, API keys, tokens).
