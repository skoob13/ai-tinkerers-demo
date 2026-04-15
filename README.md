# Hedgebox

Hedgebox is a file storage and sharing app for hedgehogs — think Dropbox, but for hedgehogs.

This is a Next.js app with login/signup flows, a file management interface, a pricing page, a Marius Tech Tips landing page, and PostHog integration for product analytics and session recording.

## Setup

1. Install dependencies:

```bash
pnpm install
```

2. Set up PostHog environment variables:

The app automatically fetches the PostHog API key from your local database at build/dev time. You can configure the database connection and team ID using these environment variables:

```env
NEXT_PUBLIC_POSTHOG_HOST # PostHog host (default: http://localhost:8010)
NEXT_PUBLIC_POSTHOG_KEY  # PostHog API key, fetched automatically on `pnpm run dev`
POSTHOG_TEAM_ID          # Team ID to fetch token from (default: latest team)
```

**Note:** The API key is automatically fetched and written to `.env.local` when you run `pnpm run dev` or `pnpm run build`. The script will skip fetching if `.env.local` already exists (to avoid unnecessary database queries on every run).

To manually fetch the key or force a re-fetch, run:

```bash
# Fetch if .env.local doesn't exist or doesn't have key NEXT_PUBLIC_POSTHOG_KEY
pnpm run fetch-posthog-key
# Force re-fetch even if NEXT_PUBLIC_POSTHOG_KEY set in .env.local
FORCE_FETCH_KEY=1 pnpm run fetch-posthog-key
```

Alternatively, you can manually create a `.env.local` file with the `NEXT_*` vars above.

3. Run the development server:

```bash
pnpm run dev
```

The app will be available at [http://localhost:3000](http://localhost:3000).
