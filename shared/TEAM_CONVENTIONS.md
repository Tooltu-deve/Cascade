# Quy ước nhóm — FreeCell Solver (CSC14003)

Tài liệu tổng hợp để cả nhóm **làm việc nhất quán** giữa frontend (React), service thuật toán (Python / FastAPI) và phần báo cáo. Chi tiết kiểu JSON và ví dụ request/response xem **`shared/API.md`**.

---

## 1. Problem formulation (formal hóa bài toán tìm kiếm)

- **Bài toán:** Từ một trạng thái bàn FreeCell hợp lệ, tìm (hoặc xấp xỉ) chuỗi nước đi dẫn tới **mục tiêu** — bốn foundation mỗi pile đủ 13 lá cùng chất từ Át tới K.
- **Không gian trạng thái:** Mỗi **node** là một `GameState` đầy đủ (8 cascade, 4 free cell, 4 foundation). Trạng thái **quan sát được toàn phần**, không có lá ẩn.
- **Trạng thái đích (goal test):** Mỗi foundation tương ứng một chất có đúng 13 lá đúng thứ tự (hoặc điều kiện tương đương: 52 lá đã nằm trên foundation).
- **Cạnh (action):** Mỗi bước đi trong đồ thị tìm kiếm là **một nước nguyên tử** — chỉ di chuyển **đúng một lá** mỗi lần (từ đỉnh cascade hoặc từ free cell), tới foundation, free cell trống, hoặc xây trên cascade/cột trống theo luật FreeCell. **Không** dùng “một action = cả chuỗi tableau hợp lệ” trong không gian successor.
- **Chi phí (UCS / A\*):** Định nghĩa rõ trong báo cáo (ví dụ mỗi nước nguyên tử cost = 1).
- **Trùng lặp trạng thái:** Dùng tập `visited` / hash trạng thái thống nhất giữa các thuật toán (mô tả cách mã hóa state trong báo cáo).

---

## 2. Cách giao tiếp giữa frontend và thuật toán

- **Tách vai trò:** React chỉ lo **hiển thị**, **input người chơi**, và **gọi HTTP** tới FastAPI. Toàn bộ BFS / DFS / UCS / A\* chạy **trên server** (Python), không chạy thuật toán tìm kiếm trong trình duyệt.
- **Định dạng trao đổi:** JSON, trường **`camelCase`**, `Content-Type: application/json`.
- **Luồng solver:** Frontend gửi **một** request `POST` kèm **toàn bộ** `state` hiện tại → server chạy hết một lần tìm kiếm (trong giới hạn timeout) → trả về **một** response gồm `ok`, `moves` (nếu có), `metrics`, `error` (nếu cần). Frontend **không** polling từng bước trong lúc server đang tính; sau khi nhận đủ response, mới **replay** từng phần tử trong `moves` trên UI (có thể làm animation).
- **Đồng bộ luật:** Nước đi trong `moves` phải áp dụng được bằng **cùng quy tắc** với phần mô phỏng trên client (hoặc client chỉ replay theo danh sách đã kiểm chứng phía server). Nếu UI cho phép kéo cả chuỗi bài (UX), đó **không** thay thế formal hóa nguyên tử: lời giải từ API vẫn là chuỗi **nước đơn**.
- **CORS:** Khi dev (Vite cổng 5173, API cổng 8000), backend bật CORS cho origin frontend.
- **Timeout:** Thống nhất giới hạn thời gian một request (mặc định đề xuất 120 giây) và cách báo lỗi (`ok: false`, `error: "timeout"`, vẫn gửi `metrics` nếu đo được). Chi tiết xem `API.md`.

---

## 3. Các API cần có (FastAPI)

Tất cả dùng **cùng body** và **cùng kiểu response**; chỉ khác **thuật toán** được gọi.

| Phương thức | Đường dẫn | Chức năng |
|-------------|-----------|-----------|
| `POST` | `/solve/bfs` | Breadth-First Search |
| `POST` | `/solve/dfs` | Depth-First Search (hoặc IDS — ghi trong báo cáo) |
| `POST` | `/solve/ucs` | Uniform-Cost Search |
| `POST` | `/solve/astar` | A* |

- **Request body:** `{ "state": <GameState> }` — xem cấu trúc `GameState` và `Card` trong `API.md`.
- **Response body:** `{ "ok": boolean, "moves"?: MoveStep[], "metrics"?: SearchMetrics, "error"?: string }` — mỗi `MoveStep` là một nước nguyên tử; `metrics` phục vụ báo cáo (thời gian, bộ nhớ đỉnh, số node mở rộng, độ dài lời giải).

Base URL dev gợi ý: `http://localhost:8000` (cấu hình qua biến môi trường phía frontend).

---

## 4. Quy ước luật chơi (game rules)

Các quy tắc dưới đây áp dụng **thống nhất** cho cả UI và engine Python (sinh successor, kiểm tra goal, replay `moves`).

- **Bộ bài:** 52 lá; `suit` ∈ `spades | hearts | diamonds | clubs`; `rank` 1–13 (1 = Át, 11–13 = J, Q, K tùy cách hiển thị).
- **Bố cục:** 8 cascade (chia bài: 4 cột 7 lá, 4 cột 6 lá theo deal chuẩn nhóm đang dùng), 4 free cell, 4 foundation theo thứ tự **♠ → ♥ → ♦ → ♣** tương ứng index `0–3`.
- **Thứ tự trong mảng:** Trong mỗi cascade và mỗi foundation, index **0 = đáy**, index cao nhất = **đỉnh** (lá có thể di chuyển từ cascade là lá đỉnh trong formal nguyên tử).
- **Tableau:** Xây xen màu, hạng giảm dần khi đi lên (7 trên 8, v.v.).
- **Foundation:** Cùng chất, tăng dần từ Át; chỉ đưa **một lá** lên foundation mỗi nước nguyên tử.
- **Free cell:** Tối đa một lá mỗi ô; chỉ chuyển **một lá** từ/đến free cell mỗi nước nguyên tử tương ứng.
- **Formal solver:** Không dùng “sequence move” như một action trong đồ thị; UI có thể cho phép kéo chuỗi vì tiện người chơi, nhưng **lời giải thuật toán** chỉ chứa các bước **một lá**; với `from.kind === 'cascade'`, `fromIndex` luôn là **đỉnh cột** tại thời điểm thực hiện bước đó.

---

## 5. Tài liệu liên quan trong repo

| File | Nội dung |
|------|----------|
| `shared/API.md` | Hợp đồng API chi tiết, ví dụ JSON, timeout, TypeScript tham chiếu |
| `shared/openapi.yaml` | (Nếu có) OpenAPI 3.1 cho import Swagger / codegen |

---

*Cập nhật tài liệu này khi nhóm thống nhất thay đổi formal hóa, timeout, hoặc schema.*
