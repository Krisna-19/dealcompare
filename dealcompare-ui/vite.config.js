import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Prevent a second React copy (root node_modules has a different version)
    // from breaking Hooks under jsdom: always resolve these from this package.
    dedupe: ['react', 'react-dom', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.js'],
    // Component tests only; the pure Node asserts (deals, filterSort) run via `npm test`.
    include: ['tests/**/*.test.jsx'],
    css: false,
  },
})