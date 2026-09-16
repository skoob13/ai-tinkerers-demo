# Hosted demo seeding plan

Status: planned. No hosted project has been configured or seeded.

## Demo scope

Give the file-storage app a coherent usage history, then capture a real exception and recording from the app so a coding agent can investigate it and propose a verifiable fix. The initial seed covers signup, login, navigation, and file activity.

## Proposed interface

Add `scripts/seed-demo.py` with two explicit modes: `generate` and `upload`. Generation is the default safe preparation step and requires no hosted credentials. Upload requires a generated manifest, an explicit target project ID, and a project ingestion token supplied through the environment. The CLI must describe these as separate operations; it must never upload as a side effect of generation.

The generator imports `HedgeboxMatrix` from a local PostHog checkout and runs in that checkout's development environment. Its adapter calls the in-memory simulation only. It must not call `MatrixManager.run_on_team`, change a local project, or copy a local database. PostHog's existing `generate_demo_data` management command persists to its local databases and is not a hosted import command.

Use small classes for generation, payload conversion, and batch upload. Keep the CLI responsible for parsing options and wiring those components together.

## Dataset

- Default to 14 days of history, an explicit UTC end time, a fixed random seed, and zero future days.
- Begin with a small number of matrix clusters. Print actual user, account, session, and event counts before upload. Preserve complete user/account histories when enforcing a configurable event-volume cap; fail and request a smaller simulation if the cap would truncate histories.
- Include the app's supported events: `$pageview`, `$pageleave`, `$autocapture`, `signed_up`, `logged_in`, `logged_out`, `uploaded_file`, `downloaded_file`, `deleted_file`, and `shared_file_link`, plus the identity and group records needed to interpret them.
- Exclude unsupported billing, subscription, experiment, AI, and synthetic error scenarios from this demo's seed.
- Namespace generated users, accounts, and sessions with a stable dataset identifier. Preserve anonymous-to-identified relationships. Use invented personas and reserved email domains such as `example.com`.
- Normalize simulated URLs to the configured demo app origin, preserving routes and query strings. Attach a stable `demo_seed_id` to imported records.

## Artifacts and identity alignment

Write artifacts to the ignored `.seed/` directory:

- `manifest.json`: schema version, source revision, seed, UTC date range, app origin, counts, event distribution, payload checksum, and stable run ID. No credentials.
- `events.jsonl`: past events in chronological order, preserving timestamps and using deterministic event UUIDs. Convert person and group metadata into the supported capture payloads rather than assuming direct database fields are accepted by the API.
- `personas.json`: a few usable demo personas with the same user and account IDs as their seeded histories.
- `upload-state.json`: target project, manifest checksum, and acknowledged batches for resumable uploads. Reject a resume against a different target or manifest.

Before importing, align app instrumentation with the matrix: emit `shared_file_link`, capture navigation pageviews, and attach account groups. Add an explicit demo-persona selection mechanism so a browser session can continue a seeded user's history. Keep analytics disabled until the hosted project configuration is supplied.

## Hosted import

1. Read the project ingestion token and region-specific ingestion host from environment configuration. Keep management credentials, if needed for verification, server-side and outside the browser configuration.
2. Validate the complete artifact set locally, including timestamps, identifiers, references, supported event names, and counts.
3. Establish the target project's identity and corresponding ingestion token before sending anything. Show the project ID, host, date range, and counts without printing tokens.
4. Send bounded batches through PostHog's documented historical batch ingestion endpoint. Configure historical import mode, remain below its payload size limit, and preserve event ordering and identities.
5. Retry transient failures with bounded exponential backoff and unchanged event UUIDs. Persist progress only after acknowledged success. An ambiguous retry must reuse the original payload; stable UUIDs and local progress tracking reduce duplicates but require verification of the destination's deduplication behavior.
6. Verify ingestion with bounded queries scoped to `demo_seed_id`: event totals and types, time range, representative users, and account relationships. API acceptance alone is not completion.

## Live exception and replay

After the analytics seed is verified, enable and verify exception capture, source maps, and session recording. Record several browser sessions using the seeded personas: ordinary files open successfully, while a file with missing metadata exercises a reproducible defect in the connected repository. Let the SDK generate the actual exception and recording. Recordings are a separate capture path; importing analytics events does not create playable replays.

Create a small dashboard for active users, file activity, and affected users through the hosted API after the project is available. Record the real exception, recording, report, and PR URLs in a local run manifest. Dashboard creation is separate from event import.

## Validation

Use isolated tests for identity conversion, timestamp bounds, credential-free manifests, deterministic retry payloads, and interrupted-upload recovery. Exercise the uploader against a local HTTP stub before one small hosted batch. Finish by checking an affected user's seeded history and live session, then verify that the generated PR builds and fixes the original reproduction while ordinary files still work.

## Inputs still needed

- Hosted project URL and its ingestion configuration.
- Final deployed or local app origin used during the demo.
- The repository connected to Self-driving and its base branch.

The seeding script must not create a hosted project, connect integrations, enable autonomous coding, or merge a PR as an implicit part of importing data.
