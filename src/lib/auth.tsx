'use client'

import React, { ReactNode, createContext, useContext, useEffect, useState } from 'react'

import { sampleUsers } from './data'
import { findDemoPersona } from './demoPersonas'
import { DemoAccountFixture, findDemoAccount, openDemoAccount } from './demoScenarios'
import { initPostHog, posthog } from './posthog'
import { nameFromEmail } from './utils'

interface User {
    id: string
    name: string
    email: string
    plan: string
    avatar?: string
    account_id?: string
    demo_seed_id?: string
    demo_scenario?: string
}

interface AuthContextType {
    user: User | null
    login: (email: string, password: string) => Promise<boolean>
    signup: (name: string, email: string, password: string, plan: string) => Promise<boolean>
    logout: () => void
    isLoading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

function identifyUser(user: User | DemoAccountFixture): void {
    initPostHog()
    if (user.demo_scenario) {
        posthog.register({ demo_scenario: user.demo_scenario, demo_synthetic: true })
    }
    posthog.identify(user.id, { name: user.name, email: user.email, plan: user.plan })
    if (user.account_id) {
        posthog.group('account', user.account_id)
    }
}

export function AuthProvider({ children }: { children: ReactNode }): React.JSX.Element {
    const [user, setUser] = useState<User | null>(null)
    const [isLoading, setIsLoading] = useState(true)

    // Load user from localStorage on mount
    useEffect(() => {
        initPostHog()
        const savedUser = localStorage.getItem('hedgebox_user')
        if (savedUser) {
            try {
                const userData = JSON.parse(savedUser)
                setUser(userData)
                // Re-identify user on page load
                identifyUser(userData)
            } catch {
                localStorage.removeItem('hedgebox_user')
            }
        }
        setIsLoading(false)
    }, [])

    const login = async (email: string): Promise<boolean> => {
        setIsLoading(true)

        try {
            await new Promise((resolve) => setTimeout(resolve, 1500))

            const demoAccount = findDemoAccount(email)
            if (demoAccount) {
                identifyUser(demoAccount)
                posthog.capture('logged_in')
                openDemoAccount(demoAccount)
                return true
            }

            let userData: User | undefined = (await findDemoPersona(email)) ?? sampleUsers.find((u) => u.email === email)
            if (!userData) {
                userData = {
                    id: `user_${Date.now()}`,
                    name: nameFromEmail(email),
                    email,
                    plan: 'personal/free',
                }
            }

            const userWithAvatar = {
                ...userData,
                avatar: `https://api.dicebear.com/7.x/adventurer/svg?seed=${encodeURIComponent(userData.email)}&backgroundColor=1e40af`,
            }

            setUser(userWithAvatar)
            localStorage.setItem('hedgebox_user', JSON.stringify(userWithAvatar))

            // Track successful login
            identifyUser(userWithAvatar)
            posthog.capture('logged_in')

            return true
        } catch {
            return false
        } finally {
            setIsLoading(false)
        }
    }

    const signup = async (name: string, email: string, password: string, plan: string): Promise<boolean> => {
        setIsLoading(true)

        try {
            // Simulate API call
            await new Promise((resolve) => setTimeout(resolve, 2000))

            const userData = {
                id: `user_${Date.now()}`,
                name,
                email,
                plan,
                avatar: `https://api.dicebear.com/7.x/adventurer/svg?seed=${encodeURIComponent(email)}&backgroundColor=1e40af`,
            }

            setUser(userData)
            localStorage.setItem('hedgebox_user', JSON.stringify(userData))

            // Track successful signup
            identifyUser(userData)
            posthog.capture('signed_up', {
                from_invite: false,
            })

            return true
        } catch {
            return false
        } finally {
            setIsLoading(false)
        }
    }

    const logout = (): void => {
        setUser(null)
        localStorage.removeItem('hedgebox_user')
        posthog.capture('logged_out')
        posthog.reset()
    }

    return <AuthContext.Provider value={{ user, login, signup, logout, isLoading }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextType {
    const context = useContext(AuthContext)
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider')
    }
    return context
}
