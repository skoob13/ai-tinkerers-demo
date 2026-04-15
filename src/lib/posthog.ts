import posthog from 'posthog-js'

export function initPostHog(): void {
    if (typeof window !== 'undefined') {
        const apiToken = process.env.NEXT_PUBLIC_POSTHOG_KEY
        if (!apiToken) {
            console.warn(
                'NEXT_PUBLIC_POSTHOG_KEY is not set, skipping PostHog initialization.\n' +
                    'Run "npm run fetch-key" to automatically fetch the key from the database.'
            )
            return
        }
        const apiHost = process.env.NEXT_PUBLIC_POSTHOG_HOST || 'http://localhost:8010'
        posthog.init(apiToken, {
            api_host: apiHost,
            disable_compression: true,
            capture_pageview: false,
            autocapture: true,
            persistence: 'memory',
            opt_out_useragent_filter: true,
        })
        console.info(`PostHog initialized for Hedgebox with host: ${apiHost}, api token: ${apiToken}`)
    }
    ;(window as any).posthog = posthog
}

export { posthog }
