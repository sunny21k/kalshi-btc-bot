# Dashboard frontend

React, TypeScript, Tailwind, and Vite. The Python dashboard server serves the
production build and `/api` endpoints.

```text
src/
  main.tsx                 React entry point and stylesheet import
  App.tsx                  Bots / Info navigation and selected bot
  api/                     Typed HTTP requests
  hooks/                   Data polling, bot actions, navigation, theme
  content/help.ts          Getting started, bot guide, FAQ
  components/
    bots/                  Workspace, controls, health, risk notes
    info/                  Product guide, searchable FAQ, releases
    layout/                Page links, header, bot sidebar, footer
    performance/           Lazy-loaded panel, chart, calendar, statistics
    results/               Result-refresh progress and errors
    stats/                 Summary panels and reusable metrics
    trades/                Trade tables, entry movement, accessible detail dialog
  types/                   Bot, trade, dashboard, and performance contracts
  lib/                     Data normalization, performance, navigation, releases
  utils/                   Shared formatting helpers
  styles/index.css         Shared palette, layout, and component styles
tests/                     Offline frontend regression tests
scripts/                   Build and release version management
release.json               Current version, source fingerprint, release history
```

`App` connects the hooks to presentation components. Components own local UI
state such as the selected chart range or an editable budget. HTTP calls live
in `api/dashboard.ts`; importing or rendering components does not start a bot.
The bot-actions hook retains input validation and the live-money confirmation.
The chart library stays behind the `BotPerformance` lazy-loading boundary.

`components/bots/BotDetails.tsx` renders the server-provided rule profile in a
collapsed native disclosure inside each bot's control panel. Rule text comes
from `src/bot_rules.py` in the repository root, using strategy constants and
runtime settings. Running rule snapshots and current-code fallbacks are
labeled separately; the frontend does not maintain another copy of thresholds.

Click a trade row or its ID button to open the native modal dialog. Escape,
the close button, or the backdrop dismisses it. `lib/entryMovement.ts` derives
the displayed BTC movement details from saved observations; historical
reconstructions stay labeled as inferred. Currency presentation uses two
decimals while numeric source data stays unchanged.

To change a table, edit `components/trades/`. To change a bot's control panel,
edit `components/bots/BotControl.tsx`. Financial calculations belong in
`lib/performance.ts`, and shared API shapes belong in `types/`. Python trading
and execution logic remains in the repository's root `src/` directory.

From this directory:

```sh
npm test
npm run build
```

For frontend development, `npm run dev` proxies `/api` requests to the existing
Python dashboard at `http://127.0.0.1:8765`. Rebuild after frontend changes when
using the Python server's production dashboard, then refresh the browser.

## Pages and help content

The header switches between **Bots** (`/bots`) and **Info & FAQ** (`/info`).
Help also works while the bot API is unavailable. Link directly to questions
with `/info/faq` or release history with `/info/updates`. The quiet version link
in the footer opens that history. Internal links use browser history without
reloading the app; Back/Forward and opening links in new tabs still work. Both
Vite and the Python server serve the app for direct page requests and refreshes.

Edit `src/content/help.ts` for guide text and questions. This release still
uses your local bot server; public accounts and shared hosting are not included.

## Versions and release notes

The starting release is **v1.0.0**. `npm run build` records a fingerprint of
frontend source, public assets, and page/build configuration. Changed content
advances the patch version (for example, v1.0.0 → v1.0.1). Rebuilding the same
content keeps the version. Live data refreshes and the development server do
not advance it.

Add a meaningful release note with a build:

```sh
npm run build -- --note="Added trade search"
```

Use minor releases for larger features and major releases for breaking changes:

```sh
npm run release:minor -- --note="Added the strategy workspace"
npm run release:major -- --note="Introduced new account settings"
```

Repeat `--note` to add multiple release notes. Without notes, changed builds
get a generic dashboard-update entry. Explicit minor/major releases advance
the version even if the source fingerprint is unchanged.

`release.json`, `package.json`, and `package-lock.json` stay synchronized. If
compilation fails, the build restores their previous contents. Commit these
files with the source changes and rebuilt `dist/` assets.

For intermediate UI checks without recording a release:

```sh
npm run build -- --no-version
```
