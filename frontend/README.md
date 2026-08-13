# Frontend

Vue 3 + TypeScript frontend with Pinia, Alova, Tailwind CSS v4, shadcn/vue,
Apache ECharts, and vue-echarts.

```powershell
pnpm install
pnpm dev
```

The Vite development server proxies `/api` to `http://127.0.0.1:8000`.
Override `VITE_API_BASE_URL` when the API is deployed elsewhere.

Run all frontend checks with:

```powershell
pnpm type-check
pnpm test
pnpm build
```

`src/components/charts/RealtimeLineChart.vue` is the reusable Canvas chart.
`src/composables/useRealtimeSeries.ts` provides batched snapshots backed by a
fixed-size ring buffer, so incoming SSE messages do not trigger one chart redraw
per message. ECharts modules are registered on demand in
`src/components/charts/echarts.ts`, and the demo page lazy-loads the chart chunk.
