import { defineConfig, loadEnv } from 'vite';

// Development-only same-origin proxy; no production CORS/auth/deployment policy.
export default defineConfig(({ mode }) => ({
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/runtime/agentarts': {
        target:
          loadEnv(mode, process.cwd(), 'AGENTARTS_BRIDGE_').AGENTARTS_BRIDGE_PROXY_TARGET ||
          'http://127.0.0.1:8766',
      },
      '/runtime': {
        target:
          loadEnv(mode, process.cwd(), 'LOCAL_RUNTIME_').LOCAL_RUNTIME_PROXY_TARGET ||
          'http://127.0.0.1:8765',
      },
    },
  },
}));
