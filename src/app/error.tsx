'use client'

import { useEffect, useRef } from 'react'

import { initPostHog, posthog } from '@/lib/posthog'

interface AppErrorProps {
    error: Error & { digest?: string }
}

export default function AppError({ error }: AppErrorProps): React.JSX.Element {
    const capturedError = useRef<Error | null>(null)

    useEffect(() => {
        if (capturedError.current !== error) {
            capturedError.current = error
            initPostHog()
            posthog.captureException(error, { error_boundary: 'app', digest: error.digest })
        }
    }, [error])

    return (
        <main className="mx-auto max-w-xl space-y-4 p-8">
            <h1 className="text-2xl font-bold">Could not open this page</h1>
            <p>Try reloading the page. If this happened during a demo, return to the setup page to clear the demo account.</p>
            <a className="btn btn-primary" href="/demo">Open demo setup</a>
        </main>
    )
}
