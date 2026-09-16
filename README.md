# Hedgebox

Hedgebox is a file storage and sharing app for hedgehogs.

This Next.js demo includes login/signup flows, a file management interface, pricing, and PostHog integration. Users and file actions are simulated in the browser; no storage backend is required.

## Run locally

Install dependencies and start the app:

```bash
pnpm install
pnpm dev
```

Open http://localhost:3000. Without a PostHog project key, analytics is disabled. Development and production builds do not query a database or modify your environment file.

## Connect PostHog

Copy `.env.example` to `.env.local`, set your project's public ingestion key and ingestion host, then restart the app. Use the host shown in your project's SDK setup instructions (for example, `https://us.i.posthog.com` or `https://eu.i.posthog.com`).

The SDK explicitly captures unhandled errors and promise rejections and allows session recording. Enable session replay in your PostHog project; its recording rules still apply. On Vercel, set `NEXT_PUBLIC_POSTHOG_KEY` and `NEXT_PUBLIC_POSTHOG_HOST` before building, then redeploy. Verify capture before using it in a demo. Connecting analytics alone does not configure Self-driving or GitHub access.

## Demo data

Use the [seeding guide](docs/seeding.md) to generate matrix data locally, import it into a hosted PostHog project, verify ingestion, and export matching demo personas. Generation does not upload anything. The [design plan](docs/seeding-plan.md) records the broader demo scope.

## Exception demos

Open `/demo` to reproduce clipboard-permission and incomplete-profile failures. See the [exception demo guide](docs/exception-demos.md) for setup, expected errors, and account reset instructions.

## Checks

```bash
python3 -m unittest discover -s scripts -p 'test_*.py'
pnpm exec tsc --noEmit
pnpm build
```
