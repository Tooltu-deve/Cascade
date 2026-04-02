/**
 * Tất cả file `web/states/*.txt` được bundle sẵn. Chọn file qua:
 * - URL: `?state=a_star` (không cần .txt)
 * - Env: `VITE_INITIAL_STATE=a_star`
 * Nếu tên không tồn tại → dùng file đầu tiên (theo tên).
 */
// Từ src/game/ phải lên ../../states (web/states/), không phải src/states/
const stateFileModules = import.meta.glob<string>('../../states/*.txt', {
  query: '?raw',
  import: 'default',
  eager: true,
})

function fileBaseName(path: string): string {
  const m = path.match(/\/([^/]+)\.txt$/)
  return m ? m[1] : path
}

const contentByName: Record<string, string> = {}
for (const [path, content] of Object.entries(stateFileModules)) {
  contentByName[fileBaseName(path)] = content
}

export function listStateFileNames(): string[] {
  return Object.keys(contentByName).sort()
}

export function getStateFileContent(name: string): string | undefined {
  const key = name.replace(/\.txt$/i, '').trim()
  return contentByName[key]
}

/** Ưu tiên ?state= rồi tới VITE_INITIAL_STATE rồi file đầu tiên. */
export function getSelectedStateName(): string {
  if (typeof window !== 'undefined') {
    const q = new URLSearchParams(window.location.search).get('state')
    if (q) return q.replace(/\.txt$/i, '').trim()
  }
  const env = import.meta.env.VITE_INITIAL_STATE?.trim()
  if (env) return env.replace(/\.txt$/i, '')
  const names = listStateFileNames()
  return names[0] ?? ''
}

export function resolveStateText(): { name: string; text: string } | null {
  let name = getSelectedStateName()
  let text = name ? getStateFileContent(name) : undefined
  if (!text) {
    const names = listStateFileNames()
    name = names[0] ?? ''
    text = name ? getStateFileContent(name) : undefined
  }
  if (!text || !name) return null
  return { name, text }
}
