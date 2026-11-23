import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// `npm run dev` proxies the API to a controller running locally (CONTROLLER_URL to override).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': process.env.CONTROLLER_URL ?? 'http://localhost:5050' },
  },
  build: { outDir: 'dist', chunkSizeWarningLimit: 800 },
});
