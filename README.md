# FreeCell Solver (AI Fundamental Project)

Dự án gồm 2 phần:

- `backend/`: FastAPI cung cấp các endpoint solver (BFS/DFS/UCS/A*)
- `web/`: Frontend React hiển thị game FreeCell và gọi API solver

---

## Yêu cầu hệ thống

- Python 3 (khuyến nghị 3.10+)
- `pip3`
- Node.js LTS + `npm`

---

## Chạy Backend (FastAPI)

```bash
cd backend
pip3 install -r requirements.txt
python3 -m uvicorn main:app --reload --port 8000
```

Backend cung cấp:

- `GET /health`
- `POST /solve/bfs`
- `POST /solve/dfs`
- `POST /solve/ucs`
- `POST /solve/astar`

---

## Chạy Frontend (React + Vite)

```bash
cd web
npm install

# Copy env (nếu chưa có)
cp .env.example .env.local

npm run dev
```

Mặc định Vite chạy ở `http://localhost:5173`.

---

## Chú ý cấu hình API URL

File `web/.env.example` có:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Nếu backend chạy ở port khác hoặc host khác, hãy chỉnh `web/.env.local` cho khớp.

---

## Chọn trạng thái game (optional)

Frontend hỗ trợ chọn file trạng thái trong `web/states/`:

- qua query param `?state=<tên-file-không-đuôi-.txt>`
- hoặc qua env `VITE_INITIAL_STATE` trong `web/.env.local`

Ví dụ: `http://localhost:5173/?state=bfs`

---

## Kiểm tra nhanh

Frontend:

```bash
cd web
npm run lint
npm run build
```

Backend tests:

```bash
cd backend
python3 run_all_tests.py
```

