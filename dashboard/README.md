# Dashboard frontend

React, TypeScript, Tailwind, and Vite. The Python dashboard server serves the
production build and `/api` endpoints.

```text
src/
  main.tsx                 React entry point and stylesheet import
  App.tsx                  Dashboard composition and selected bot
  api/                     Typed HTTP requests
  hooks/                   Data polling, bot actions, result sync, theme
  components/
    bots/                  Workspace, controls, health, risk notes
    layout/                Header, bot sidebar, footer
    performance/           Lazy-loaded panel, chart, calendar, statistics
    results/               Result-refresh progress and errors
    stats/                 Summary panels and reusable metrics
    trades/                Trade tables and shared table presentation
  types/                   Bot, trade, dashboard, and performance contracts
  lib/                     Data normalization and performance calculations
  utils/                   Shared formatting helpers
  styles/index.css         Shared palette, layout, and component styles
tests/                     Offline frontend regression tests
```

`App` connects the hooks to presentation components. Components own local UI
state such as the selected chart range or an editable budget. HTTP calls live
in `api/dashboard.ts`; importing or rendering components does not start a bot.
The bot-actions hook retains input validation and the live-money confirmation.
The chart library stays behind the `BotPerformance` lazy-loading boundary.

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
