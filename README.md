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

Enable session replay and error tracking in your PostHog project and verify their capture settings before using them in a demo. Connecting analytics alone does not configure Self-driving or GitHub access.

## Demo data

The [seeding plan](docs/seeding-plan.md) describes the planned synthetic data generator and hosted-project importer. Seeding is not implemented yet.

## Checks

```bash
pnpm exec tsc --noEmit
pnpm build
```
