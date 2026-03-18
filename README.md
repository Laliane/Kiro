# Backend
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Frontend (outro terminal)
cd frontend
npm install
npm run dev
