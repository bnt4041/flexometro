import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Los bind mounts de Docker Desktop en Windows no propagan eventos inotify;
    // sin polling el hot reload no se entera de los cambios.
    watch: { usePolling: true, interval: 300 },
    // El proxy evita CORS en desarrollo y reproduce lo que hará Traefik en
    // producción: un único origen sirviendo web y API.
    proxy: {
      '/api': { target: 'http://api:8000', changeOrigin: true },
      '/health': { target: 'http://api:8000', changeOrigin: true },
    },
  },
})
