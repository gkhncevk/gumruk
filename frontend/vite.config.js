import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 'npm run dev' ile calisirken /api istekleri Node backend'e (port 3000)
    // yonlendirilir, boylece gelistirme sirasinda CORS ugrasmana gerek kalmaz.
    // Production'da zaten backend frontend/dist'i dogrudan servis ediyor,
    // bu proxy sadece 'npm run dev' icin gecerli.
    proxy: {
      '/api': {
        target: 'http://localhost:3000',
        changeOrigin: true,
      },
    },
  },
})
