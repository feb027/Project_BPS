import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Embed the build stamp (injected via vite define) into the bundle so every
// production build gets a unique entry/chunk hash. This busts any front CDN
// (Cloudflare) cache that would otherwise keep serving a stale chunk when
// only a lazy chunk (e.g. ChartModal) was changed. Assigned (not just
// referenced) so it is not tree-shaken away.
;(window as unknown as { __BUILD_STAMP__?: string }).__BUILD_STAMP__ = __BUILD_STAMP__

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
