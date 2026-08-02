import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { SWRConfig } from 'swr'
import './index.css'
import App from './App.tsx'

// Embed the build stamp (injected via vite define) into the bundle so every
// production build gets a unique entry/chunk hash. This busts any front CDN
// (Cloudflare) cache that would otherwise keep serving a stale chunk when
// only a lazy chunk (e.g. ChartModal) was changed. Assigned (not just
// referenced) so it is not tree-shaken away.
;(window as unknown as { __BUILD_STAMP__?: string }).__BUILD_STAMP__ = __BUILD_STAMP__

// SWR global: data statistik jarang berubah — jangan refetch tiap kali tab
// kembali fokus (hemat bandwidth di jaringan BPS), dan dedupe request
// identik dalam 10 detik.
const swrConfig = {
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
  dedupingInterval: 10_000,
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SWRConfig value={swrConfig}>
      <App />
    </SWRConfig>
  </StrictMode>,
)
