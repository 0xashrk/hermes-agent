/**
 * Wallet data layer. One read: `GET /api/plugins/askgina_os/overview`, served by
 * `plugins/askgina_os/dashboard/plugin_api.py` through `ctx.rest`. The backend
 * holds the os agent token; this side only ever sees the summary below.
 */

import {
  host,
  type PluginOs,
  type PluginRestOptions,
  type PluginTranslate,
  queryClient,
  useValue
} from '@hermes/plugin-sdk'

import { bindMessages, type WalletText } from './i18n'

type Rest = <T>(path: string, opts?: PluginRestOptions) => Promise<T>

export interface WalletLimit {
  chainId: string
  symbol: string
  perPayment: string
  perDay: string
}

export interface WalletInfo {
  walletId: string
  address: string
  label: null | string
  isDefault: boolean
  hasPolicy: boolean
  approvalsNeeded: null | number
  limits: WalletLimit[]
  recipients: null | string
}

export interface MandateInfo {
  mandateId: string
  purpose: null | string
  recipients: string[]
  usesLeft: number
  notAfter: number
  assets: { symbol: string; perPayment: string; total: string; usedTotal: string }[]
}

export interface IntentRow {
  intentId: string
  status: string
  title: null | string
  amount: null | string
  asset: null | string
  to: null | string
  memo: null | string
  createdAt: null | number | string
  authorizedBy: 'mandate' | 'person'
  explorerUrl: null | string
  failureCode: null | string
  approvalPage?: string
}

export interface WalletOverview {
  configured: boolean
  baseUrl: null | string
  tokenSet?: boolean
  error?: string
  agent?: { name: null | string }
  wallets?: WalletInfo[]
  balances?: { chainId: string; symbol: string; amount: string }[]
  mandates?: MandateInfo[]
  pending?: IntentRow[]
  recent?: IntentRow[]
}

export const DEFAULT_OS_URL = 'http://localhost:8080'

// Every query is keyed by the ACTIVE CONNECTION: `ctx.rest` routes to the active
// gateway/profile, so a connection switch must be a clean cache miss, never the
// previous profile's balances or approval links (the kanban/hermes-bots pattern).
const KEY_ROOT = ['askgina_os'] as const
const LOCAL_SCOPE = 'local'

export function useWalletScope(): string {
  return useValue(host.state.connectionId) ?? LOCAL_SCOPE
}

export const overviewKey = (scope: string) => [...KEY_ROOT, 'overview', scope] as const

/** Where a request issued NOW is routed. Queries only fetch while their key's scope is this one, so
 *  a switch never writes the incoming gateway's payload under the outgoing connection's key. */
const routedScope = (): string => host.activeConnectionId() ?? LOCAL_SCOPE
const routedToScope = (query: { queryKey: readonly unknown[] }): boolean => query.queryKey[2] === routedScope()

let rest: null | Rest = null
let os: null | PluginOs = null
let text: null | WalletText = null
// Pending approvals already announced, per connection; a scope absent here has not been polled yet,
// so opening the app with payments already waiting doesn't fire a burst of notifications.
const announced = new Map<string, Set<string>>()

export function bindApi(r: Rest, o: PluginOs, t: PluginTranslate): () => void {
  rest = r
  os = o
  text = bindMessages(t)
  announced.clear()
  queryClient.setQueryDefaults(KEY_ROOT, { enabled: routedToScope })

  return () => {
    queryClient.setQueryDefaults(KEY_ROOT, {})
    rest = null
    os = null
    text = null
    announced.clear()
  }
}

/** Raise a native notification for each payment that newly started waiting for a person. */
function announceNewPending(scope: string, overview: WalletOverview): void {
  const pending = overview.pending ?? []
  const seen = announced.get(scope)

  if (seen && text) {
    for (const item of pending) {
      if (!seen.has(item.intentId)) {
        const amount = `${item.amount ?? ''} ${item.asset ?? ''}`.trim()
        os?.notify({ title: text.notifyTitle, body: text.notifyBody(amount, item.to ?? text.recipient) })
      }
    }
  }

  announced.set(scope, new Set(pending.map(item => item.intentId)))
}

export async function fetchOverview(scope: string): Promise<WalletOverview> {
  if (!rest) {
    throw new Error('Wallet plugin is not loaded')
  }

  const overview = await rest<WalletOverview>('/overview')

  // A switch between the call and its answer: the answer belongs to the incoming gateway, not this
  // scope, so it must not be announced under it.
  if (routedScope() === scope) {
    announceNewPending(scope, overview)
  }

  return overview
}

/** Approvals always happen in the system browser, on os's own pages — never inside Hermes. */
export function openInBrowser(url: string): void {
  void os?.openExternal(url)
}
