# Tanam Secukupnya — task runner

test:
    cd backend && uv run pytest -q

# Regenerate the synthetic dataset (deterministic seed)
data:
    uv run --project backend python scripts/generate.py

# Run the API locally on :8100 (JSON seed store, auth off, no GCP needed)
api:
    cd backend && AUTH=off uv run uvicorn app.main:app --reload --port 8100

# G1 benchmark: labeled notes → Gemini → field-level accuracy (needs ADC: gcloud auth application-default login)
eval set="dev" model="":
    uv run --project backend python scripts/eval_g1.py {{set}} {{model}}

# Load data/seed into Firestore (replaces reference collections; leaves visitors' workspaces alone)
seed-firestore:
    uv run --project backend python scripts/seed_firestore.py

project := "tanam-secukupnya"
region := "asia-southeast2"

# Build + deploy everything: API image (Cloud Build) → Cloud Run → static UI → Firebase Hosting, then smoke-test
deploy: test
    gcloud builds submit --config cloudbuild.yaml --project {{project}} \
      --service-account projects/{{project}}/serviceAccounts/tanam-build@{{project}}.iam.gserviceaccount.com
    gcloud run deploy tanam-api --image {{region}}-docker.pkg.dev/{{project}}/tanam/api:latest \
      --region {{region}} --project {{project}} --update-env-vars STORE=firestore,AUTH=on
    cd frontend && npm run build
    firebase deploy --only hosting --project {{project}}
    curl -fsS https://{{project}}.web.app/api/health && echo
    test "$(curl -s -o /dev/null -w '%{http_code}' https://{{project}}.web.app/api/state)" = 401 && echo "auth required: OK"
