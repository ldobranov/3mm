# 3mm — Мултифункционална платформа с FastAPI и Vue 3

Проектът **3mm** има за цел да бъде модулна система, която позволява лесно добавяне на функционалности като блог, онлайн магазин, домашна автоматизация и индустриален мониторинг чрез динамични добавки (extensions).

## 🛠 Стек

- **Backend:** FastAPI + Pydantic + SQLite
- **Frontend:** Vue 3 + Vite + TailwindCSS
- **UI Framework:** TailwindCSS (преди Bootstrap)
- **Системни модули:** 
  - User Manager (с роли)
  - Settings мениджър
  - Dynamic Menu Editor
  - Extension Generator (в разработка)

## 📦 Инсталация

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # или venv\Scripts\activate за Windows
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
