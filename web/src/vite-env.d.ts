/// <reference types="vite/client" />

declare module '*.txt?raw' {
  const content: string
  export default content
}

interface ImportMetaEnv {
  /** Base URL của FastAPI, ví dụ http://localhost:8000 (không có dấu / cuối) */
  readonly VITE_API_BASE_URL?: string
  /** Tên file trong `web/states/` (không cần .txt), ví dụ a_star — có thể ghi đè bằng ?state= */
  readonly VITE_INITIAL_STATE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
