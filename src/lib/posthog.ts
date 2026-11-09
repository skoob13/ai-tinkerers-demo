import posthog from 'posthog-js'

// Public ingestion key of the Hedgebox demo project. NEXT_PUBLIC_POSTHOG_KEY overrides it.
const DEFAULT_POSTHOG_KEY = 'phc_qixEfPaCLsAjWbfpCKBHALF6vzgY2YMLJFU9gU6kBTHa'

export function initPostHog(): void {
    if (typeof window === 'undefined') {
        return
    }

    if (!posthog.__loaded) {
        const apiToken = process.env.NEXT_PUBLIC_POSTHOG_KEY || DEFAULT_POSTHOG_KEY
        const apiHost = process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://us.i.posthog.com'
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
