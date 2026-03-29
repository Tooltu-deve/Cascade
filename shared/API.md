# FreeCell Solver — tài liệu API (FastAPI ↔ Frontend)

Tài liệu này mô tả các **endpoint** mà service Python (FastAPI) cần cung cấp và **cấu trúc JSON** trao đổi với frontend (React). Mọi payload dùng **`Content-Type: application/json`**, tên trường **`camelCase`** để khớp TypeScript.

---

## 1. Quy ước kỹ thuật

| Mục | Giá trị |
|-----|--------|
| Base URL (dev) | `http://localhost:8000` (tuỳ cấu hình Uvicorn) |
| Encoding | UTF-8 |
| Request body | JSON object |
| Thứ tự foundation | `0 = ♠ spades`, `1 = ♥ hearts`, `2 = ♦ diamonds`, `3 = ♣ clubs` |

**Trạng thái bàn (`GameState`):**

- `cascades[c][i]`: cột `c` (0–7), chỉ số `i` từ **đáy** (= 0) lên **đỉnh** (= `length - 1`).
- `freeCells`: đúng 4 ô, phần tử là lá bài hoặc `null` (ô trống).
- `foundations[s]`: pile chất `s`, thứ tự trong mảng từ **đáy lên đỉnh** (Át ở index 0 khi đã có).

---

## 2. Quy tắc chung (solver, luật chơi, formal hóa)

Các quy tắc dưới đây **bắt buộc thống nhất** giữa nhóm frontend, backend và phần báo cáo (mô tả bài toán tìm kiếm).

### 2.1. Luật chơi dùng chung

- **Một nguồn sự thật:** logic chuyển trạng thái hợp lệ (foundation, cascade, free cell, kiểm tra thắng, v.v.) phải **khớp nhau** giữa UI và Python. Khuyến nghị: tái sử dụng cùng đặc tả / module kiểm thử (ví dụ bộ ván cố định, so sánh hash trạng thái sau từng nước).
- **Định dạng trạng thái:** `GameState` trong API (mục 5) phải là biểu diễn **đầy đủ** để cả hai phía suy ra cùng tập nước đi hợp lệ.

### 2.2. Không dùng “sequence move” trong không gian tìm kiếm

- Trong **đồ thị trạng thái** dùng cho BFS / DFS / UCS / A\*, mỗi **cạnh** (một bước đi) chỉ được phép là nước **nguyên tử**: mỗi lần chỉ di chuyển **đúng một lá** — từ **đỉnh** một cascade, hoặc từ một free cell, tới foundation / free cell trống / đỉnh cascade khác / cột trống theo đúng luật FreeCell cho **một lá**.
- **Không** coi việc “nhấc cả một chuỗi hợp lệ trên tableau trong một lần” là **một** action khi sinh successor. Trên giao diện, người chơi có thể kéo cả chuỗi (UX), nhưng phía solver **không** mở rộng trạng thái theo kiểu đó; nếu cần mô phỏng chuỗi, phải tách thành **nhiều** nước nguyên tử nối tiếp nhau trong không gian tìm kiếm.

### 2.3. Chuỗi nước đi trong `SolveResponse.moves`

- Mỗi phần tử `MoveStep` tương ứng **một** nước nguyên tử.
- Với `from.kind === 'cascade'`, **`fromIndex` luôn là chỉ số lá trên cùng** của cột đó (tức `fromIndex === cascades[col].length - 1` tại thời điểm thực hiện nước đi đó). Không trả các bước kiểu “cắt chuỗi từ giữa cột” trong lời giải thuật toán theo formal hóa này.

### 2.4. Timeout và giới hạn tài nguyên

| Quy tắc | Đề xuất (team có thể chỉnh bằng biến môi trường) |
|--------|-----------------------------------------------|
| **Thời gian tối đa một request solver** | Mặc định **120 giây** (wall-clock) tính từ lúc bắt đầu tìm kiếm đến khi trả HTTP. Hết hạn → `ok: false`, `error: "timeout"`, vẫn trả `metrics.searchTimeMs` và các chỉ số đã thu thập được (nếu có). |
| **Giới hạn bổ sung (tuỳ chọn)** | Ví dụ `maxExpandedNodes` để dừng sớm khi bộ nhớ/thời gian tăng quá nhanh; khi chạm ngưỡng → `ok: false`, `error` ghi rõ (ví dụ `"node_limit"`). |
| **Ghi nhận trong báo cáo** | Nêu rõ timeout và mọi giới hạn đã dùng khi so sánh thuật toán. |

### 2.5. Hành vi khi lỗi / không tìm được đường

- Trạng thái không hợp lệ (không đủ 52 lá, cấu trúc sai): `422` hoặc `400` + mô tả; hoặc `200` với `ok: false`, `error: "invalid_state"` — **thống nhất một cách** trong team.
- Hết thời gian / hết giới hạn node / không có lời giải trong phạm vi đã tìm: `ok: false`, `moves` rỗng hoặc bỏ qua, `metrics` vẫn hữu ích cho thí nghiệm.

---

## 3. Danh sách endpoint (solver)

Tất cả đều là **`POST`**, **cùng một kiểu body** (`SolveRequest`), **cùng một kiểu response** (`SolveResponse`). Khác nhau chỉ **thuật toán** chạy phía server.

| Phương thức | Đường dẫn | Mô tả |
|-------------|-----------|--------|
| `POST` | `/solve/bfs` | Breadth-First Search |
| `POST` | `/solve/dfs` | Depth-First Search (hoặc IDS — ghi trong báo cáo) |
| `POST` | `/solve/ucs` | Uniform-Cost Search |
| `POST` | `/solve/astar` | A* |

**Gợi ý frontend:** ghép URL `POST ${API_BASE}/solve/${method}` với `method ∈ { bfs, dfs, ucs, astar }`.

---

## 4. Request — `SolveRequest`

Gửi **một object** có trường bắt buộc `state` (trạng thái bàn cần giải).

### 4.1. Cấu trúc tổng quát

```json
{
  "state": { /* GameState — xem mục 5 */ }
}
```

### 4.2. TypeScript (tham chiếu)

```ts
interface SolveRequest {
  state: GameState
}
```

---

## 5. Kiểu `GameState` (trong `state`)

```ts
interface GameState {
  cascades: Card[][]    // đúng 8 phần tử
  freeCells: (Card | null)[]  // đúng 4 phần tử
  foundations: [Card[], Card[], Card[], Card[]]  // 4 pile: ♠ ♥ ♦ ♣
}

interface Card {
  suit: 'spades' | 'hearts' | 'diamonds' | 'clubs'
  rank: number  // 1 = Át … 13 = K
}
```

**Ràng buộc:** `cascades.length === 8`, `freeCells.length === 4`, `foundations.length === 4`; mỗi `rank` trong `1..13`.

---

## 6. Response — `SolveResponse`

Server trả về sau khi kết thúc tìm kiếm (hoặc timeout / lỗi).

```ts
interface SolveResponse {
  ok: boolean
  moves?: MoveStep[]      // thứ tự nước đi để frontend replay; rỗng nếu không tìm được
  metrics?: SearchMetrics
  error?: string            // ví dụ: "timeout", "unsolvable", "invalid_state"
}
```

### 6.1. `MoveStep` (một nước đi nguyên tử)

Mỗi bước tương ứng **một** lần áp dụng luật (xem mục 2). Cấu trúc giống `Selection` + `MoveTarget` trong code game, với ràng buộc **cascade chỉ từ đỉnh** (mục 2.3).

```ts
interface MoveStep {
  from: Selection
  to: MoveTarget
}

type Selection =
  | { kind: 'cascade'; col: number; fromIndex: number }
  | { kind: 'freecell'; slot: number }

type MoveTarget =
  | { kind: 'foundation'; suitIndex: number }
  | { kind: 'freecell'; slot: number }
  | { kind: 'cascade'; col: number }
```

- Với `from.kind === 'cascade'`: `fromIndex` **luôn** là chỉ số lá **trên cùng** của cột `col` tại thời điểm thực hiện bước đó.
- `suitIndex`: `0..3` khớp thứ tự foundation ở mục 1.
- `col`, `slot`: `0..7` và `0..3` tương ứng.

### 6.2. `SearchMetrics` (đo lường — theo yêu cầu đồ án)

```ts
interface SearchMetrics {
  searchTimeMs: number       // thời gian tìm kiếm (ms)
  peakMemoryBytes: number    // bộ nhớ đỉnh (byte) — định nghĩa cách đo trong báo cáo
  expandedNodes: number      // số node đã mở rộng
  solutionLength: number      // số nước trong `moves` (0 nếu không có lời giải)
}
```

Khi `ok === false`, vẫn nên trả `metrics` (nếu đo được) và `error` ngắn gọn.

---

## 7. Ví dụ

### 7.1. Request tối thiểu (khung)

```http
POST /solve/bfs HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "state": {
    "cascades": [ /* 8 cột, mỗi cột mảng Card */ ],
    "freeCells": [ null, null, null, null ],
    "foundations": [ [], [], [], [] ]
  }
}
```

### 7.2. Response có lời giải (rút gọn)

```json
{
  "ok": true,
  "moves": [
    {
      "from": { "kind": "cascade", "col": 2, "fromIndex": 6 },
      "to": { "kind": "foundation", "suitIndex": 1 }
    }
  ],
  "metrics": {
    "searchTimeMs": 1250.5,
    "peakMemoryBytes": 52428800,
    "expandedNodes": 150000,
    "solutionLength": 1
  }
}
```

*(Trong ví dụ trên, `fromIndex: 6` nghĩa là cột 2 có 7 lá và lá trên cùng có index 6.)*

---

## 8. Ghi chú triển khai

1. **CORS:** Nếu frontend chạy cổng khác (ví dụ Vite `5173`), FastAPI cần bật `CORSMiddleware` cho origin dev.
2. **Replay trên UI:** Frontend áp dụng từng phần tử `moves` theo thứ tự bằng cùng luật với backend (mục 2.1). Nếu UI cho phép kéo cả chuỗi, không được coi đó là một bước tương đương một phần tử của `moves` trừ khi đã tách thành nhiều bước nguyên tử.
3. **Bản máy đọc được:** Có thể bổ sung file `shared/openapi.yaml` (OpenAPI 3.1) để sinh client/server hoặc import vào Swagger UI của FastAPI.

---

*Tài liệu này định nghĩa hợp đồng giữa React và service solver; chỉnh sửa khi team thống nhất thay đổi schema hoặc quy tắc formal hóa.*
