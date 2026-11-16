/**
 * Plugin-scoped i18n for the Wallet — bundles registered under the plugin id via
 * ctx.i18n.register, never touching core en.ts. `useWallet()` binds the
 * stringly-typed plugin translator to the message SHAPE (the kanban pattern).
 * Other locales fall back to English.
 */

import { type PluginLocaleBundles, type PluginTranslate, usePluginI18n } from '@hermes/plugin-sdk'
import { useMemo } from 'react'

export const PLUGIN_ID = 'askgina_os'

type WalletMessages = {
  nav: string
  openCommand: string
  title: string
  agent: (name: string) => string
  openOs: string
  loadFailed: (reason: string) => string
  retry: string
  pendingTitle: (count: number) => string
  pendingHint: string
  pendingEmpty: string
  pendingTip: string
  pendingPill: (count: number) => string
  reviewApprove: string
  noMemo: string
  memo: (memo: string) => string
  payment: string
  wallet: string
  defaultWallet: string
  noWallet: string
  address: string
  copyAddress: string
  balance: (chainId: string) => string
  noPolicy: string
  setLimits: string
  changeLimits: string
  limit: (symbol: string) => string
  limitValue: (perPayment: string, perDay: string) => string
  recipients: string
  approvalsNeeded: string
  mandatesTitle: string
  mandatesHint: string
  mandatesEmpty: string
  mandate: string
  mandateAsset: (perPayment: string, symbol: string, used: string, total: string) => string
  mandateTerms: (usesLeft: number, recipients: string, until: string) => string
  recentTitle: string
  recentEmpty: string
  byMandate: string
  byPerson: string
  needsPerson: string
  openExplorer: string
  connectTitle: string
  connectBody: string
  connectButton: string
  connecting: string
  tryAgain: string
  pairCode: string
  pairWaiting: string
  openAgain: string
  cancel: string
  pairDenied: string
  pairExpired: string
  pairConnected: string
  advanced: string
  osAddress: string
  notifyTitle: string
  notifyBody: (amount: string, to: string) => string
  recipient: string
}

const en: WalletMessages = {
  nav: 'Wallet',
  openCommand: 'Wallet: Open',
  title: 'Wallet',
  agent: name => `agent: ${name}`,
  openOs: 'Open askgina/os',
  loadFailed: reason => `Couldn't load the wallet: ${reason}`,
  retry: 'Retry',
  pendingTitle: count => `Waiting for your approval (${count})`,
  pendingHint: "Hermes can't approve; only your passkey can",
  pendingEmpty: 'Nothing waiting. When Hermes proposes a payment, it shows up here.',
  pendingTip: 'Payments waiting for your passkey approval',
  pendingPill: count => `${count} waiting for approval`,
  reviewApprove: 'Review & approve',
  noMemo: 'No memo',
  memo: memo => `“${memo}”`,
  payment: 'Payment',
  wallet: 'Wallet',
  defaultWallet: 'default wallet',
  noWallet: 'No wallet yet.',
  address: 'Address',
  copyAddress: 'Copy address',
  balance: chainId => `Balance (${chainId})`,
  noPolicy: "No limits yet: this wallet can't pay until you set them.",
  setLimits: 'Set limits',
  changeLimits: 'Change limits',
  limit: symbol => `Limit (${symbol})`,
  limitValue: (perPayment, perDay) => `${perPayment} per payment · ${perDay} per day`,
  recipients: 'Recipients',
  approvalsNeeded: 'Approvals needed',
  mandatesTitle: 'Mandates',
  mandatesHint: 'pre-approved: signed with no prompt, within these limits',
  mandatesEmpty: 'None. Every payment needs your approval.',
  mandate: 'Mandate',
  mandateAsset: (perPayment, symbol, used, total) =>
    `up to ${perPayment} ${symbol} per payment · used ${used} of ${total}`,
  mandateTerms: (usesLeft, recipients, until) => `${usesLeft} payment(s) left · to ${recipients} · until ${until}`,
  recentTitle: 'Recent payments',
  recentEmpty: 'No payments yet.',
  byMandate: 'covered by a mandate',
  byPerson: 'approved by a person',
  needsPerson: "needed a person's approval",
  openExplorer: 'Open in block explorer',
  connectTitle: 'Connect a wallet',
  connectBody:
    'Hermes pays through askgina/os, a signer you run. Hermes only asks; you approve each payment with your passkey. It never holds a key.',
  connectButton: 'Connect wallet',
  connecting: 'Connecting…',
  tryAgain: 'Try again',
  pairCode: 'Check this code matches in your browser, then press Allow.',
  pairWaiting: 'Waiting for you to allow it…',
  openAgain: 'Open again',
  cancel: 'Cancel',
  pairDenied: 'Not connected: you chose not to allow it.',
  pairExpired: 'The code expired.',
  pairConnected: 'Connected.',
  advanced: 'Advanced',
  osAddress: 'askgina/os address',
  notifyTitle: 'Hermes needs your approval',
  notifyBody: (amount, to) => `${amount} → ${to}. Open the Wallet to review.`,
  recipient: 'recipient'
}

export const WALLET_LOCALES: PluginLocaleBundles = { en }

// Bind the message SHAPE to a plugin translator: string leaves resolve now,
// function leaves forward their args through t(path, …).
type Bound<T> = { [K in keyof T]: T[K] extends (...args: infer A) => string ? (...args: A) => string : string }

export function bindMessages(t: PluginTranslate): WalletText {
  const out = {} as Record<string, unknown>

  for (const [key, value] of Object.entries(en)) {
    out[key] = typeof value === 'function' ? (...args: unknown[]) => t(key, ...args) : t(key)
  }

  return out as WalletText
}

export type WalletText = Bound<WalletMessages>

/** The Wallet strings for the active locale. */
export function useWallet(): WalletText {
  const t = usePluginI18n(PLUGIN_ID)

  return useMemo(() => bindMessages(t), [t])
}
