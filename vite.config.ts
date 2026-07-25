import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  clearScreen: false,
  server: {
    host: '127.0.0.1',
    port: 1420,
    strictPort: true,
  },
  preview: {
    host: '127.0.0.1',
    port: 1420,
    strictPort: true,
  },
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        countdown: fileURLToPath(new URL('./countdown.html', import.meta.url)),
      },
    },
  },
})
