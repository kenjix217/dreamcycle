import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.DREAMCYCLE_DASHBOARD_API_URL || 'http://127.0.0.1:8765';

  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: false,
      proxy: {
        '/dreamcycle-api': {
          target,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/dreamcycle-api/, ''),
        },
      },
    },
    preview: {
      port: 4173,
      strictPort: false,
      proxy: {
        '/dreamcycle-api': {
          target,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/dreamcycle-api/, ''),
        },
      },
    },
  };
});
