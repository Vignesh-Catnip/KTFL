# SAP MIRO Invoice Processing POC — Ollama Edition

Professional local-AI POC based on the supplied MIRO wireframe and process workbook.

## Stack
- React + TypeScript + Vite + Tailwind CSS
- FastAPI + Pydantic + SQLAlchemy
- PostgreSQL / pgAdmin
- Ollama + local vision model for invoice extraction
- Mock RPA adapter for safe local testing

## 1. PostgreSQL / pgAdmin
Create a database:
```sql
CREATE DATABASE miro_invoice;
```
Copy `backend/.env.example` to `backend/.env` and set your PostgreSQL password.

## 2. Install Ollama (Windows)
1. Install Ollama from the official Ollama website: https://ollama.com/download/windows
2. Open CMD/PowerShell and verify:
```powershell
ollama --version
```
3. Pull a vision model. Recommended starting point:
```powershell
ollama pull llama3.2-vision:11b
```
4. Verify the local API:
```powershell
curl http://localhost:11434/api/tags
```
Keep the Ollama application/service running while testing.

> Model size and RAM/VRAM requirements depend on the model. If your PC cannot comfortably run the 11B vision model, choose a smaller vision model available in your Ollama installation and set `OLLAMA_MODEL` accordingly.

## 3. Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs
Health: http://localhost:8000/health

## 4. Frontend
Open another terminal:
```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```
Open http://localhost:5173

## 5. First test WITHOUT AI
Set:
```env
EXTRACTION_MODE=demo
RPA_MODE=mock
```
Upload `sample_invoices/sample_invoice.pdf`.
This confirms the complete UI/API/database flow before adding Ollama.

## 6. Test with Ollama
Stop/restart FastAPI after changing `.env`:
```env
EXTRACTION_MODE=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2-vision:11b
OLLAMA_TIMEOUT=180
OLLAMA_MAX_PAGES=3
```
Upload a clear PDF/JPG/PNG invoice. FastAPI converts PDF pages to images, sends them to Ollama, parses JSON, validates the result, checks duplicates, and saves it to PostgreSQL.

## 7. MIRO business flow
Upload → Ollama extraction → duplicate check → validation → human review → approve/send-back → mock RPA processing → history/exception.

Validation includes required extraction fields, total/line consistency, and confidence checks. The UI never claims a real SAP posting when `RPA_MODE=mock`.

## 8. Important Ollama note
This project uses Ollama, not a paid cloud OCR service. Ollama itself is the local runtime; the selected model is downloaded and run on your machine. There is no API key in this project.

The invoice extraction prompt intentionally asks the model not to invent values. Low-confidence or incomplete extraction should be routed to human review.

## 9. Real SAP/RPA
`backend/app/services/rpa.py` is an adapter boundary. Keep `RPA_MODE=mock` for development. Add your organization's approved RPA/SAP endpoint and authentication only after the SAP/RPA contract is available. Do not put SAP passwords in frontend code.

## 10. Troubleshooting
- `Connection refused 11434`: start Ollama.
- `model not found`: run `ollama pull <model>` and make `OLLAMA_MODEL` match exactly.
- PDF extraction error: test a clear invoice PDF or JPG/PNG.
- PostgreSQL error: verify database name, username, password and port in `DATABASE_URL`.
- CORS error: ensure `CORS_ORIGINS=http://localhost:5173` and restart FastAPI.
