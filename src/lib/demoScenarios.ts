import { posthog } from './posthog'

export interface DemoAccountFixture {
    id: string
    email: string
    name?: string
    plan: string
    demo_scenario: string
    account_id?: string
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

export function findDemoAccount(email: string): DemoAccountFixture | undefined {
    return Object.values(accounts).find((account) => account.email === email.trim().toLowerCase())
}

export function openDemoAccount(account: DemoAccountFixture): void {
    localStorage.setItem('hedgebox_user', JSON.stringify(account))
    const embeddedWorkspace = account.demo_scenario === 'clipboard-permission-denied' && window.self === window.top
    window.location.assign(embeddedWorkspace ? '/workspace' : '/files')
}

export function startDemoScenario(scenario: 'clipboard' | 'profile'): void {
    posthog.reset()
    openDemoAccount(accounts[scenario])
}

export function resetDemoScenario(): void {
    localStorage.removeItem('hedgebox_user')
    posthog.reset()
    window.location.assign('/login')
}
