# Seed a hosted Hedgebox demo

The seeder generates synthetic analytics with PostHog's Hedgebox matrix, then imports them through the historical capture API. Generation, uploading, and verification are separate commands. It does not create a hosted project, change a database, fabricate session recordings, or create dashboards, exceptions, reports, or PRs.

Generation requires a working PostHog checkout and its Python development environment. Validation, persona export, uploading, verification, and unit tests use only the Python standard library (Python 3.11 or later on macOS/Linux).

## Generate and inspect

From the PostHog repository root, with this app in `../hedgebox`:

```bash
.codex/with-flox python ../hedgebox/scripts/seed-demo.py generate \
  --posthog-repo . \
  --app-origin https://your-demo.example.com \
  --end 2026-09-16T00:00:00Z \
  --days 30 \
  --clusters 20 \
  --output ../hedgebox/.seed/demo
```

Replace the origin and UTC end time for your demo. The default is 14 days, 20 clusters, and a maximum of 20,000 events. The matrix's short windows can be sparse: inspect the actual event and identified-user counts rather than assuming one cluster equals one active user. Generation rejects future end times and refuses to overwrite an existing output directory. The simulation's beginning is rounded down to UTC midnight, as recorded in the manifest.

The exporter blocks Django database queries during initialization and simulation and uses test settings to suppress startup jobs. It only reads the in-memory matrix events. An unresolved conflict or missing dependency in the PostHog checkout can still prevent importing the matrix; resolve the checkout before generating.

The output directory contains `events.jsonl`, `personas.json`, and `manifest.json`. The manifest records the source revision, matrix and exporter checksums, generation options, counts, and file checksums. Dataset identities are scoped to these inputs. Keep the generated directory for all retries instead of regenerating it.

From the Hedgebox repository root, validate a dataset without accessing the network:

```bash
python3 scripts/seed-demo.py validate --input .seed/demo
```

The dataset includes navigation, signup/login, file activity, and the identify/group records they need. It excludes matrix billing, experiment exposures, AI generations, and fabricated exceptions. File routes describe simulated historical files and do not populate the app's browser-only file list. Analytics events do not produce playable recordings.

## Configure the target

The uploader uses three explicit inputs:

- `--project-id`: the hosted PostHog project ID.
- `--region us` or `--region eu`: selects the official management and ingestion hosts.
- `--env-file .env.local`: reads the ingestion token from `NEXT_PUBLIC_POSTHOG_KEY` and a management credential from `POSTHOG_PERSONAL_API_KEY`. Process environment values override the file.

Use a personal API key with access to the target project and the `project:read` and `query:read` scopes. The uploader retrieves the project and confirms that its ingestion token matches before sending events. The verification command uses the query API. Do not prefix the management key with `NEXT_PUBLIC_` or include it in a deployment's client settings.

The env-file parser supports simple `KEY=value` lines, optional surrounding quotes, and full-line comments. It does not execute shell substitutions, expand variables, or support inline comments. Credentials are never written to generated artifacts or logged. Upload progress stores only a token fingerprint.

## Upload and verify

Start with a small batch:

```bash
python3 scripts/seed-demo.py upload \
  --input .seed/demo --project-id YOUR_PROJECT_ID --region us \
  --env-file .env.local --limit 100
```

Continue the same dataset by repeating the command without `--limit`:

```bash
python3 scripts/seed-demo.py upload \
  --input .seed/demo --project-id YOUR_PROJECT_ID --region us \
  --env-file .env.local
```

Uploads are sequential, capped at 200 events and 1 MB per batch, and use `historical_migration: true`. `upload-state.json` binds acknowledged progress to the project, region, token fingerprint, and manifest. Concurrent uploaders are refused. Transient failures retry the identical payload with stable event UUIDs; HTTP acceptance saves a checkpoint but does not prove ingestion. If a response is lost after the server accepted it, a retry can replay that batch. Verification detects duplicate UUIDs; do not delete progress files and start again to fix a partial upload.

After ingestion has caught up:

```bash
python3 scripts/seed-demo.py verify \
  --input .seed/demo --project-id YOUR_PROJECT_ID --region us \
  --env-file .env.local
```

Verification scopes queries to the dataset and date range and forces fresh results instead of reading the query cache. It checks per-event totals, duplicate UUIDs, anonymous-to-identified person relationships, and account associations on events. It writes `verification.json` and returns a nonzero exit code for incomplete ingestion or mismatches. Retrying verification is read-only. It does not validate recordings or prove the existence of a real application bug.

## Continue a seeded user's history in the app

After choosing the dataset to import, export a small public persona list:

```bash
python3 scripts/seed-demo.py export-personas \
  --input .seed/demo --output public/demo-personas.json --limit 5
```

This explicitly replaces the destination file. It contains only generated names, reserved `example.com` emails, user/account IDs, plan names, and the dataset ID. Review and commit this file when deploying the corresponding seeded demo. The checked-in default is an empty array.

Log in with an email from that file and any nonempty password. This is the app's simulated login, not authentication. The app identifies the same seeded person and attaches the same account group. A missing seeded persona produces a login error instead of silently inventing a new identity. Ordinary demo logins continue to work without a persona file.

The app emits `shared_file_link` and captures navigation pageviews to match the matrix. Live sessions are separate from the historical import: record them through the SDK after enabling the hosted project's replay and error settings.

## Tests

```bash
python3 -m unittest discover -s scripts -p 'test_*.py'
pnpm exec tsc --noEmit
pnpm build
```

The seeder tests use synthetic fixtures and a fake HTTP boundary; they need no Django setup, database, hosted project, or credentials.

API reference: [Capture and historical batches](https://posthog.com/docs/api/capture#batch-events).
