import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/assets/dashboard/',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    proxy: {
      '/debug': 'http://127.0.0.1:18765',
      '/health': 'http://127.0.0.1:18765',
      '/v1': 'http://127.0.0.1:18765',
    },
  },
});
