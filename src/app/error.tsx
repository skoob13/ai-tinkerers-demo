'use client'

import { useEffect, useRef, useState } from 'react'

import { resetDemoScenario } from '@/lib/demoScenarios'

import { initPostHog, posthog } from '@/lib/posthog'

interface AppErrorProps {
    error: Error & { digest?: string }
}

export default function AppError({ error }: AppErrorProps): React.JSX.Element {
    const capturedError = useRef<Error | null>(null)
    const [isLeaving, setIsLeaving] = useState(false)
    const [resetError, setResetError] = useState(false)

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
            <p>Your workspace could not load. Sign out and try another account.</p>
            {resetError && <p role="alert">Could not sign out. Allow browser storage and try again.</p>}
            <button
                className="btn btn-primary"
                disabled={isLeaving}
                onClick={() => {
                    setIsLeaving(true)
                    setResetError(false)
                    try {
                        resetDemoScenario()
                    } catch {
                        setResetError(true)
                        setIsLeaving(false)
                    }
                }}
            >
                {isLeaving ? 'Signing out...' : 'Sign out and return to login'}
            </button>
        </main>
    )
}
