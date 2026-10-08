import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // Handle redirects from backend - rewrite location header to stay on /api path
        configure: (proxy, _options) => {
          proxy.on('proxyRes', (proxyRes, _req, _res) => {
            const location = proxyRes.headers['location']
            if (location && location.includes('://backend:8000')) {
              proxyRes.headers['location'] = location.replace('http://backend:8000', '/api')
            }
          })
        },
      },
      '/skill.md': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        headers: {
          'X-Requested-With': 'VeroFrontend'
        },
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
