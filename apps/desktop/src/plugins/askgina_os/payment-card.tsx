/**
 * The in-chat payment card: `::askgina-payment{intent="int_…"}` in an assistant
 * message renders this. The directive's attributes are model output, so the
 * card takes only the payment id from them and reads everything it shows
 * (amount, recipient, status, the approval page) from os through the
 * backend. Approving still happens on os's own page in the system browser.
 */

import { Badge, Button, Codicon, type TranscriptDirectiveProps, useQuery } from '@hermes/plugin-sdk'

import { fetchIntent, intentKey, type IntentRow, openInBrowser, useWalletScope } from './api'
import { useWallet, type WalletText } from './i18n'

const POLL_MS = 3000
const INTENT_ID = /^int_[0-9a-z]{26}$/

function short(address: null | string | undefined): string {
  return address && address.length > 14 ? `${address.slice(0, 6)}…${address.slice(-4)}` : (address ?? '')
}

function tone(intent: IntentRow): 'destructive' | 'muted' | 'success' | 'warn' {
  if (intent.status === 'confirmed') {
    return 'success'
  }

  if (['denied', 'failed', 'rejected', 'reverted'].includes(intent.status)) {
    return 'destructive'
  }

  return intent.final ? 'muted' : 'warn'
}

function statusText(w: WalletText, intent: IntentRow): string {
  if (intent.approvalPage) {
    return w.cardWaiting
  }

  return intent.status === 'confirmed' ? w.cardConfirmed : intent.status.replace(/_/g, ' ')
}

export function PaymentCard({ attrs }: TranscriptDirectiveProps) {
  const w = useWallet()
  const scope = useWalletScope()
  const intentId = attrs.intent ?? ''
  const valid = INTENT_ID.test(intentId)

  const query = useQuery({
    queryKey: intentKey(scope, intentId),
    queryFn: () => fetchIntent(intentId),
    enabled: valid,
    refetchInterval: q => {
      const data = q.state.data

      return data && ('error' in data || data.final) ? false : POLL_MS
    }
  })

  if (!valid) {
    return null
  }

  const data = query.data

  if (!data || 'error' in data) {
    return (
      <div className="my-2 rounded-lg border border-(--ui-stroke-secondary) px-4 py-3 text-xs text-muted-foreground">
        {data ? w.cardUnavailable(data.error) : w.cardLoading}
      </div>
    )
  }

  return (
    <div className="my-2 flex max-w-xl flex-wrap items-center gap-4 rounded-xl border border-(--ui-stroke-secondary) bg-(--ui-bg-secondary) px-4 py-3">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-(--ui-bg-tertiary)">
        <Codicon name="credit-card" size="1rem" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold">
          {data.amount ? `${data.amount} ${data.asset ?? ''}` : (data.title ?? w.payment)}
          {data.to && <span className="font-normal text-muted-foreground"> → {short(data.to)}</span>}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant={tone(data)}>{statusText(w, data)}</Badge>
          {data.memo && <span className="truncate">{w.memo(data.memo)}</span>}
          {data.failureCode && <span>{data.failureCode}</span>}
        </div>
      </div>
      {data.approvalPage ? (
        <Button onClick={() => openInBrowser(data.approvalPage!)} size="sm">
          <Codicon name="link-external" size="0.8rem" />
          {w.reviewApprove}
        </Button>
      ) : data.explorerUrl ? (
        <Button onClick={() => openInBrowser(data.explorerUrl!)} size="sm" variant="secondary">
          <Codicon name="link-external" size="0.8rem" />
          {w.cardViewTransaction}
        </Button>
      ) : null}
    </div>
  )
}
