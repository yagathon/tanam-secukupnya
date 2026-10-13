# Tanam Secukupnya — task runner

test:
    cd backend && uv run pytest -q

# Regenerate the synthetic dataset (deterministic seed)
data:
    uv run --project backend python scripts/generate.py

# Run the API locally on :8100 (JSON seed store, no GCP needed)
api:
    cd backend && uv run uvicorn app.main:app --reload --port 8100

# G1 benchmark: labeled notes → Gemini → field-level accuracy (needs ADC: gcloud auth application-default login)
eval set="dev" model="":
    uv run --project backend python scripts/eval_g1.py {{set}} {{model}}
