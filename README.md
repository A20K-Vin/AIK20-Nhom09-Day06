# Lab6 - Huong Dan Chay Full Web App

README nay huong dan chay day du **backend API + frontend UI** de su dung full web app.

## Cau Truc Chinh

- `backend/app/main.py`: entrypoint FastAPI
- `backend/app/routers/`: API cho chat, doctors, appointments, sessions
- `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`: giao dien web
- `backend/crawl/crawl_v2.py`: crawl lich bac si qua API noi bo (tuy chon)

## Yeu Cau

- Python 3.10+ (khuyen nghi)
- pip
- Trinh duyet (Chrome/Edge/Firefox)

## 1. Cai Dat Backend

Mo terminal tai thu muc goc du an `src`, sau do chay:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Neu dung endpoint AI chat (`/api/chat`), can them bien moi truong:

```powershell
set OPENAI_API_KEY=your_openai_api_key
```

## 2. Chay Backend API

Trong thu muc `backend`, chay:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Kiem tra nhanh backend:

```text
http://localhost:8000/
```

Neu backend chay dung se tra ve:

```json
{"message":"MediFlow API is running"}
```

## 3. Chay Frontend

Mo terminal moi tai thu muc goc `src`, chay:

```powershell
cd frontend
python -m http.server 3000
```

Mo trinh duyet:

```text
http://localhost:3000
```

## 4. Chay Full Web App

- Terminal 1: backend o cong `8000`
- Terminal 2: frontend o cong `3000`
- Vao `http://localhost:3000` de chat, nhan goi y bac si, va dat lich

Luu y: frontend dang goi API theo `API_BASE = "http://localhost:8000/api"` trong `frontend/app.js`.

## 5. Crawl Du Lieu Lich (Tuy Chon)

Neu can cap nhat du lieu lich bac si qua API noi bo Vinmec:

```powershell
cd backend\crawl
python crawl_v2.py
```

File output:

- `data/schedule.json`

## Su Co Thuong Gap

- Loi CORS: backend da bat CORS `allow_origins=["*"]`; dam bao backend dang chay dung cong `8000`.
- Frontend khong goi duoc API: kiem tra `API_BASE` trong `frontend/app.js` va backend URL.
- Loi module khi chay backend: kich hoat lai `.venv` va cai lai `pip install -r backend/requirements.txt`.
