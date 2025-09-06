import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 180_000,
  expect: { timeout: 90_000 },
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:8501',
    headless: true,
    viewport: { width: 1280, height: 900 },
  },
  webServer: {
    command:
      'poetry run streamlit run agrogame/dashboard/app.py --server.address 127.0.0.1 --server.headless true --server.port 8501',
    url: 'http://127.0.0.1:8501',
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
    env: {
      STREAMLIT_BROWSER_GATHER_USAGE_STATS: 'false',
    },
  },
});


