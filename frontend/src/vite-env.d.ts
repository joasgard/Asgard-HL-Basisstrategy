/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_BOT_API_URL: string;
  readonly VITE_PRIVY_APP_ID: string;
  readonly VITE_ENV: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
