# Tanam Secukupnya — task runner

test:
    cd backend && uv run pytest -q

# Regenerate the synthetic dataset (deterministic seed)
data:
    uv run --project backend python scripts/generate.py

# Run the API locally on :8100 (JSON seed store, no GCP needed)
api:
    cd backend && uv run uvicorn app.main:app --reload --port 8100
