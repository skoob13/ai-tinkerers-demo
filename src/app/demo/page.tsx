'use client'

import { useState } from 'react'

import { resetDemoScenario, startDemoScenario } from '@/lib/demoScenarios'

export default function DemoPage(): React.JSX.Element {
    const [isStarting, setIsStarting] = useState(false)
    const [error, setError] = useState('')

    const start = (scenario: 'clipboard' | 'profile' | 'reset'): void => {
        if (isStarting) {
            return
        }
        setIsStarting(true)
        setError('')
        try {
            if (scenario === 'reset') {
                resetDemoScenario()
            } else {
                startDemoScenario(scenario)
            }
        } catch {
            setError('Could not prepare the account. Allow browser storage and try again.')
            setIsStarting(false)
        }
    }

    return (
        <main className="mx-auto max-w-3xl space-y-6 p-8">
            <h1 className="text-3xl font-bold">Exception demos</h1>
            <p>Each scenario replaces the demo account in this browser with a synthetic account.</p>
            {error && <p role="alert" className="alert alert-error">{error}</p>}
            <section className="card bg-base-200 p-6 space-y-3">
                <h2 className="text-xl font-semibold">Clipboard access denied</h2>
                <p>Open a file in an embedded workspace where the browser blocks clipboard writes. Choose Share, then Copy.</p>
                <button disabled={isStarting} className="btn btn-primary" onClick={() => start('clipboard')}>
                    Open clipboard scenario
                </button>
            </section>
            <section className="card bg-base-200 p-6 space-y-3">
                <h2 className="text-xl font-semibold">Account without a display name</h2>
                <p>Restore an incomplete account profile and open the files page.</p>
                <button disabled={isStarting} className="btn btn-primary" onClick={() => start('profile')}>
                    Open profile scenario
                </button>
            </section>
            <button disabled={isStarting} className="btn btn-outline" onClick={() => start('reset')}>
                Clear demo account
            </button>
        </main>
    )
}
