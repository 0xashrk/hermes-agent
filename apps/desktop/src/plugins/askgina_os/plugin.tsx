/**
 * askgina/os Wallet — a `/wallet` page, a sidebar row and a status-bar pill
 * ("N waiting for approval") over the `askgina_os` plugin's backend router.
 * Hermes proposes payments over MCP; a person approves each one with a passkey
 * on os's own page (opened in the system browser), or a mandate covers it.
 *
 * On by default in this fork: it shows a "Connect a wallet" page until
 * `hermes askgina-os connect` has run.
 */

import {
  Codicon,
  type HermesPlugin,
  host,
  PALETTE_AREA,
  type PaletteContribution,
  type RouteContribution,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  type SidebarNavContribution,
  STATUSBAR_AREAS,
  Tip
} from '@hermes/plugin-sdk'

import { bindApi } from './api'
import { PLUGIN_ID, useWallet, WALLET_LOCALES } from './i18n'
import { useOverview, WalletPage } from './wallet'

const PATH = '/wallet'

// Status-bar pill. The native "Hermes needs your approval" notification is raised
// by the shared overview query (api.ts), so it fires wherever you are in the app.
function PendingPill() {
  const w = useWallet()
  const { data } = useOverview()
  const waiting = data?.pending?.length ?? 0

  if (waiting === 0) {
    return null
  }

  return (
    <Tip label={w.pendingTip}>
      <button
        className="inline-flex items-center gap-1 rounded px-1.5 text-amber-600 hover:bg-(--chrome-action-hover) dark:text-amber-300"
        onClick={() => host.navigate(PATH)}
        type="button"
      >
        <Codicon name="credit-card" size="0.7rem" />
        {w.pendingPill(waiting)}
      </button>
    </Tip>
  )
}

const plugin: HermesPlugin = {
  id: PLUGIN_ID,
  name: 'Wallet (askgina/os)',
  description: 'Payments through askgina/os: balances, limits, mandates, and payments waiting for your passkey.',
  defaultEnabled: true,
  register(ctx) {
    ctx.i18n.register(WALLET_LOCALES)
    ctx.onDispose(bindApi(ctx.rest, ctx.os, ctx.i18n.t))

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: PATH } satisfies RouteContribution,
        render: () => <WalletPage />
      },
      {
        id: 'pending',
        area: STATUSBAR_AREAS.right,
        order: 70,
        render: () => <PendingPill />
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 45,
        data: { codicon: 'credit-card', label: ctx.i18n.t('nav'), path: PATH } satisfies SidebarNavContribution
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'askgina_os.openWallet',
          label: ctx.i18n.t('openCommand'),
          keywords: ['wallet', 'payments', 'approve', 'askgina', 'os', 'balance'],
          run: () => host.navigate(PATH)
        } satisfies PaletteContribution
      }
    ])
  }
}

export default plugin
