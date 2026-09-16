import { posthog } from './posthog'

export interface DemoAccountFixture {
    id: string
    email: string
    name?: string
    plan: string
    demo_scenario: string
}

const accounts: Record<string, DemoAccountFixture> = {
    clipboard: {
        id: 'demo-clipboard-permission-v1',
        email: 'clipboard-user@example.com',
        name: 'Robin Demo',
        plan: 'personal/free',
        demo_scenario: 'clipboard-permission-denied',
    },
    profile: {
        id: 'demo-legacy-profile-v1',
        email: 'legacy-profile@example.com',
        plan: 'personal/free',
        demo_scenario: 'missing-display-name',
    },
}

export function startDemoScenario(scenario: 'clipboard' | 'profile'): void {
    posthog.reset()
    localStorage.setItem('hedgebox_user', JSON.stringify(accounts[scenario]))
    window.location.assign(scenario === 'clipboard' ? '/demo/clipboard' : '/files')
}

export function resetDemoScenario(): void {
    localStorage.removeItem('hedgebox_user')
    posthog.reset()
    window.location.assign('/login')
}
