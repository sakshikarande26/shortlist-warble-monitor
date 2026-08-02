import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Native FSEvents watching in this environment fires phantom "file
    // changed" events for vite.config.ts/.env/tsconfig.json with no actual
    // mtime change, causing a restart loop that eventually breaks the dev
    // server. Polling checks real mtimes on an interval instead of
    // trusting OS-level change notifications, which sidesteps it.
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
})
