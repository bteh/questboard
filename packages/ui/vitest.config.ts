import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    /* globals let testing-library register its afterEach cleanup */
    globals: true,
    include: ['src/**/*.test.tsx'],
    setupFiles: ['./vitest.setup.ts'],
  },
})
