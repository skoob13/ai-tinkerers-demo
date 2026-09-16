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
        const apiHost = process.env.NEXT_PUBLIC_POSTHOG_HOST || 'http://localhost:8010'
        posthog.init(apiToken, {
            api_host: apiHost,
            disable_compression: true,
            capture_pageview: 'history_change',
            autocapture: true,
            capture_exceptions: true,
            disable_session_recording: false,
            persistence: 'memory',
            opt_out_useragent_filter: true,
        })
        console.info(`PostHog initialized for Hedgebox with host: ${apiHost}`)
    }
    Object.assign(window, { posthog })
}

export { posthog }
