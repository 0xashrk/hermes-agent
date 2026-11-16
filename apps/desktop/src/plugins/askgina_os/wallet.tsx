/**
 * The Wallet page: what Hermes may spend through askgina/os, what is waiting for
 * a person, and what already happened. Hermes can only propose; every approval
 * button opens os's own page in the system browser, where a person approves with
 * a passkey. This page never sees the agent token.
 */

import { Badge, Button, Codicon, CopyButton, Input, ScrollArea, Skeleton, useQuery } from '@hermes/plugin-sdk'
import { type ReactNode, useState } from 'react'

import {
  cancelPairing,
  DEFAULT_OS_URL,
  fetchOverview,
  type IntentRow,
  type MandateInfo,
  openInBrowser,
  overviewKey,
  pairKey,
  type PairStart,
  pollPairing,
  refreshOverview,
  resetPairing,
  startPairing,
  useWalletScope,
  type WalletInfo,
  type WalletOverview
} from './api'
import { useWallet, type WalletText } from './i18n'

const POLL_MS = 4000
const PAIR_POLL_MS = 2000

const STATUS_TONE: Record<string, 'destructive' | 'muted' | 'success' | 'warn'> = {
  confirmed: 'success',
  approved: 'warn',
  signed: 'warn',
  broadcast: 'warn',
  stuck: 'warn',
  pending_approval: 'warn',
  proposed: 'warn',
  rejected: 'destructive',
  denied: 'destructive',
  failed: 'destructive',
  reverted: 'destructive',
  expired: 'muted',
  cancelled: 'muted',
  voided: 'muted'
}

// Statuses a payment only reaches after it was authorized. Anything else (rejected, denied,
// expired, cancelled, failed before approval) must not claim a person approved it.
const AUTHORIZED_STATUSES = new Set(['approved', 'signed', 'broadcast', 'stuck', 'confirmed', 'reverted'])

export function useOverview() {
  const scope = useWalletScope()

  return useQuery({ queryKey: overviewKey(scope), queryFn: () => fetchOverview(scope), refetchInterval: POLL_MS })
}

function short(address: null | string | undefined): string {
  return address && address.length > 14 ? `${address.slice(0, 6)}…${address.slice(-4)}` : (address ?? '—')
}

function authorizationLabel(w: WalletText, item: IntentRow): string {
  if (item.authorizedBy === 'mandate') {
    return w.byMandate
  }

  return AUTHORIZED_STATUSES.has(item.status) ? w.byPerson : w.needsPerson
}

function when(value: IntentRow['createdAt']): string {
  if (value === null || value === undefined) {
    return ''
  }

  const date = typeof value === 'number' ? new Date(value < 1e12 ? value * 1000 : value) : new Date(value)

  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function amountOf(w: WalletText, item: IntentRow): string {
  return item.amount ? `${item.amount} ${item.asset ?? ''}`.trim() : (item.title ?? w.payment)
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-(--ui-stroke-secondary) bg-(--ui-bg-secondary) p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h2>
        {hint && <span className="text-[0.7rem] text-muted-foreground">{hint}</span>}
      </div>
      {children}
    </section>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  )
}

function Pending({ items }: { items: IntentRow[] }) {
  const w = useWallet()

  return (
    <Section hint={w.pendingHint} title={w.pendingTitle(items.length)}>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{w.pendingEmpty}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map(item => (
            <li
              className="flex items-center justify-between gap-4 rounded-md bg-amber-500/10 px-3 py-2"
              key={item.intentId}
            >
              <div className="min-w-0">
                <div className="text-sm font-medium">
                  {amountOf(w, item)}
                  {item.to && <span className="font-normal text-muted-foreground"> → {short(item.to)}</span>}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {item.memo ? w.memo(item.memo) : w.noMemo} · {when(item.createdAt)}
                </div>
              </div>
              {item.approvalPage && (
                <Button onClick={() => openInBrowser(item.approvalPage!)} size="sm">
                  <Codicon name="link-external" size="0.8rem" />
                  {w.reviewApprove}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

function Wallet({ wallet, balances }: { wallet: WalletInfo; balances: WalletOverview['balances'] }) {
  const w = useWallet()

  return (
    <Section hint={wallet.isDefault ? w.defaultWallet : undefined} title={w.wallet}>
      <Row label={w.address}>
        <span className="inline-flex items-center gap-1 font-mono text-xs">
          {short(wallet.address)}
          <CopyButton label={w.copyAddress} text={wallet.address} />
        </span>
      </Row>
      {(balances ?? []).map(balance => (
        <Row key={`${balance.chainId}:${balance.symbol}`} label={w.balance(balance.chainId)}>
          <span className="font-medium tabular-nums">
            {balance.amount} {balance.symbol}
          </span>
        </Row>
      ))}
      {!wallet.hasPolicy && <p className="mt-2 text-xs text-amber-600 dark:text-amber-300">{w.noPolicy}</p>}
      {wallet.limits.map(limit => (
        <Row key={`${limit.chainId}:${limit.symbol}`} label={w.limit(limit.symbol)}>
          {w.limitValue(limit.perPayment, limit.perDay)}
        </Row>
      ))}
      {wallet.recipients && <Row label={w.recipients}>{wallet.recipients}</Row>}
      {wallet.approvalsNeeded !== null && <Row label={w.approvalsNeeded}>{wallet.approvalsNeeded}</Row>}
    </Section>
  )
}

function Mandates({ items }: { items: MandateInfo[] }) {
  const w = useWallet()

  return (
    <Section hint={w.mandatesHint} title={w.mandatesTitle}>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{w.mandatesEmpty}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map(mandate => (
            <li className="rounded-md bg-(--ui-bg-tertiary) px-3 py-2 text-sm" key={mandate.mandateId}>
              <div className="font-medium">{mandate.purpose || w.mandate}</div>
              {mandate.assets.map(asset => (
                <div className="text-xs text-muted-foreground" key={asset.symbol}>
                  {w.mandateAsset(asset.perPayment, asset.symbol, asset.usedTotal, asset.total)}
                </div>
              ))}
              <div className="text-xs text-muted-foreground">
                {w.mandateTerms(
                  mandate.usesLeft,
                  mandate.recipients.map(short).join(', '),
                  new Date(mandate.notAfter * 1000).toLocaleString()
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

function Recent({ items }: { items: IntentRow[] }) {
  const w = useWallet()

  return (
    <Section title={w.recentTitle}>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{w.recentEmpty}</p>
      ) : (
        <ul className="divide-y divide-(--ui-stroke-secondary)">
          {items.map(item => (
            <li className="flex items-center justify-between gap-3 py-2 text-sm" key={item.intentId}>
              <div className="min-w-0">
                <span className="font-medium">{amountOf(w, item)}</span>
                {item.to && <span className="text-muted-foreground"> → {short(item.to)}</span>}
                <div className="text-xs text-muted-foreground">
                  {[authorizationLabel(w, item), when(item.createdAt), item.failureCode].filter(Boolean).join(' · ')}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge variant={STATUS_TONE[item.status] ?? 'muted'}>{item.status.replace('_', ' ')}</Badge>
                {item.explorerUrl && (
                  <Button
                    aria-label={w.openExplorer}
                    onClick={() => openInBrowser(item.explorerUrl!)}
                    size="sm"
                    title={w.openExplorer}
                    variant="ghost"
                  >
                    <Codicon name="link-external" size="0.8rem" />
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

/**
 * Not connected yet: one button. It asks os for a pairing, opens os's page in the
 * browser and shows the same code here; once the person presses Allow there, the
 * backend collects the token by itself and the wallet appears.
 */
function NotConnected({ overview }: { overview: WalletOverview }) {
  const w = useWallet()
  const scope = useWalletScope()
  const [baseUrl, setBaseUrl] = useState(overview.baseUrl ?? DEFAULT_OS_URL)
  const [started, setStarted] = useState<null | PairStart>(null)
  const [starting, setStarting] = useState(false)
  const waiting = started?.status === 'pending'

  const poll = useQuery({
    queryKey: pairKey(scope),
    queryFn: async () => {
      const result = await pollPairing()

      if (result.status === 'connected') {
        void refreshOverview(scope)
      }

      return result
    },
    enabled: waiting,
    refetchInterval: query => (!query.state.data || query.state.data.status === 'pending' ? PAIR_POLL_MS : false)
  })

  const ended = poll.data && poll.data.status !== 'pending' ? poll.data : null

  const begin = async () => {
    setStarting(true)
    resetPairing(scope)

    try {
      const result = await startPairing(baseUrl)
      setStarted(result)

      if (result.status === 'pending' && result.verificationUrl) {
        openInBrowser(result.verificationUrl)
      }
    } catch (error) {
      setStarted({ status: 'error', error: error instanceof Error ? error.message : String(error) })
    } finally {
      setStarting(false)
    }
  }

  const stop = () => {
    void cancelPairing()
    resetPairing(scope)
    setStarted(null)
  }

  if (waiting && !ended) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-5 px-6 py-14 text-center">
        <h1 className="text-lg font-semibold">{w.connectTitle}</h1>
        <p className="text-sm text-muted-foreground">{w.pairCode}</p>
        <p className="rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-secondary) px-6 py-4 font-mono text-3xl font-semibold tracking-[0.2em]">
          {started.userCode}
        </p>
        <p className="inline-flex items-center gap-2 text-xs text-muted-foreground">
          <Codicon className="animate-spin" name="loading" size="0.8rem" />
          {w.pairWaiting}
        </p>
        <div className="flex gap-2">
          {started.verificationUrl && (
            <Button onClick={() => openInBrowser(started.verificationUrl!)} size="sm" variant="secondary">
              <Codicon name="link-external" size="0.8rem" />
              {w.openAgain}
            </Button>
          )}
          <Button onClick={stop} size="sm" variant="ghost">
            {w.cancel}
          </Button>
        </div>
      </div>
    )
  }

  const problem =
    ended?.status === 'denied'
      ? w.pairDenied
      : ended?.status === 'expired' || ended?.status === 'none'
        ? w.pairExpired
        : (ended?.error ?? (started?.status === 'error' ? started.error : overview.error))

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 px-6 py-14 text-center">
      <Codicon name="credit-card" size="1.5rem" />
      <h1 className="text-lg font-semibold">{w.connectTitle}</h1>
      <p className="text-sm text-muted-foreground">{w.connectBody}</p>
      {ended?.status === 'connected' ? (
        <p className="text-sm text-emerald-600 dark:text-emerald-300">{w.pairConnected}</p>
      ) : (
        <Button disabled={starting} onClick={() => void begin()}>
          {starting ? w.connecting : started || ended ? w.tryAgain : w.connectButton}
        </Button>
      )}
      {problem && <p className="text-xs text-destructive">{problem}</p>}
      <details className="w-full text-left text-xs text-muted-foreground">
        <summary className="cursor-pointer select-none text-center">{w.advanced}</summary>
        <label className="mt-2 flex flex-col gap-1">
          {w.osAddress}
          <Input onChange={event => setBaseUrl(event.target.value)} value={baseUrl} />
        </label>
      </details>
    </div>
  )
}

export function WalletPage() {
  const w = useWallet()
  const { data, error, isLoading, refetch } = useOverview()

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-start gap-2 p-6 text-sm">
        <p className="text-destructive">{w.loadFailed(error instanceof Error ? error.message : '—')}</p>
        <Button onClick={() => void refetch()} size="sm" variant="secondary">
          {w.retry}
        </Button>
      </div>
    )
  }

  if (!data.configured) {
    return <NotConnected overview={data} />
  }

  const wallet = data.wallets?.find(item => item.isDefault) ?? data.wallets?.[0]

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
        <header className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Codicon name="credit-card" size="1rem" />
            <h1 className="text-lg font-semibold">{w.title}</h1>
            {data.agent?.name && <Badge variant="muted">{w.agent(data.agent.name)}</Badge>}
          </div>
          {data.baseUrl && (
            <Button onClick={() => openInBrowser(data.baseUrl!)} size="sm" variant="secondary">
              <Codicon name="link-external" size="0.8rem" />
              {w.openOs}
            </Button>
          )}
        </header>
        {data.error ? (
          <p className="text-sm text-destructive">{data.error}</p>
        ) : (
          <>
            <Pending items={data.pending ?? []} />
            <div className="grid gap-4 md:grid-cols-2">
              {wallet ? (
                <Wallet balances={data.balances} wallet={wallet} />
              ) : (
                <Section title={w.wallet}>
                  <p className="text-sm text-muted-foreground">{w.noWallet}</p>
                </Section>
              )}
              <Mandates items={data.mandates ?? []} />
            </div>
            <Recent items={data.recent ?? []} />
          </>
        )}
      </div>
    </ScrollArea>
  )
}
