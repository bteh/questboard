import { defineConfig } from 'vitest/config'
import path from 'path'

// Standalone vitest config so unit tests skip the React/Tailwind plugins in
// vite.config.ts. Only the '@' alias is needed to resolve source imports.
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
