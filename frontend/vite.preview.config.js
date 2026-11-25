// Runtime preview uses only production dependencies; keep /api on the same origin.
export default {
  preview: {
    host: '0.0.0.0',
    port: 4173,
    strictPort: true,
    allowedHosts: ['nkb-mb-pm2p-1.tail54c504.ts.net', 'nkb-mb-pm2p-1'],
    proxy: { '/api': { target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8001' } },
  },
}
