import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dev server proxies /api to Flask, so the browser makes same-origin requests.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:5000', changeOrigin: false } },
  },
});
