const posthogHost = (process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://us.i.posthog.com').replace(/\/$/, '')
// PostHog Cloud serves static assets from a separate host, for example us-assets.i.posthog.com.
const posthogAssetsHost = posthogHost.replace('.i.posthog.com', '-assets.i.posthog.com')

/** @type {import('next').NextConfig} */
module.exports = {
    async rewrites() {
        return [
            { source: '/ingest/static/:path*', destination: `${posthogAssetsHost}/static/:path*` },
            { source: '/ingest/array/:path*', destination: `${posthogAssetsHost}/array/:path*` },
            { source: '/ingest/:path*', destination: `${posthogHost}/:path*` },
        ]
    },
    // PostHog endpoints use trailing slashes.
    skipTrailingSlashRedirect: true,
}
