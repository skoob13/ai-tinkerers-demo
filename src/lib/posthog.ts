import posthog from 'posthog-js'

export function initPostHog(): void {
    if (typeof window === 'undefined') {
        return
    }

    if (!posthog.__loaded) {
        const apiToken = process.env.NEXT_PUBLIC_POSTHOG_KEY
        if (!apiToken) {
            console.info('Analytics is disabled. Set NEXT_PUBLIC_POSTHOG_KEY in .env.local to enable it.')
            return
        }
        const ingestionHost = process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://us.i.posthog.com'
        // next.config.js forwards /ingest to the ingestion host, so ad blockers do not drop capture requests.
        posthog.init(apiToken, {
            api_host: '/ingest',
            ui_host: ingestionHost.replace('.i.posthog.com', '.posthog.com'),
            disable_compression: true,
            capture_pageview: 'history_change',
            autocapture: true,
            capture_exceptions: true,
            disable_session_recording: false,
            persistence: 'memory',
            opt_out_useragent_filter: true,
        })
        console.info(`PostHog initialized for Hedgebox through /ingest to ${ingestionHost}`)
    }
    Object.assign(window, { posthog })
}

export { posthog }
