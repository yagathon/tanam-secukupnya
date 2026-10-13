# Tanam Secukupnya — task runner

test:
    cd backend && uv run pytest -q

# Regenerate the synthetic dataset (deterministic seed)
data:
    uv run --project backend python scripts/generate.py
