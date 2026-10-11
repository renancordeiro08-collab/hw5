import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The board always runs on 5173 (the backend's CORS allows exactly this origin).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
})
