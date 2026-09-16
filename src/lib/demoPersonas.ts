import { HedgeboxUser } from '@/types'

export interface DemoPersona extends HedgeboxUser {
    account_id: string
    demo_seed_id: string
}

export async function findDemoPersona(email: string): Promise<DemoPersona | undefined> {
    if (!/^hb-[0-9a-f]{20}-user-[0-9a-f]{20}@example\.com$/.test(email)) {
        return undefined
    }
    const response = await fetch('/demo-personas.json', { cache: 'no-store' })
    if (!response.ok) {
        throw new Error('Demo personas are not available')
    }
    const personas: DemoPersona[] = await response.json()
    const persona = personas.find((candidate) => candidate.email === email)
    if (!persona?.id || !persona.account_id || !persona.demo_seed_id) {
        throw new Error('Demo persona was not found')
    }
    return persona
}
