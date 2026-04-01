/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL của FastAPI, ví dụ http://localhost:8000 (không có dấu / cuối) */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
