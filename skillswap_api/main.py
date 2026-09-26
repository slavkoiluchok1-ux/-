from fastapi import FastAPI
from src.database.db import engine, Base
from src.routes import users, skills, exchanges, stats

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SkillSwap API")

app.include_router(users.router, prefix="/api")
app.include_router(skills.router, prefix="/api")
app.include_router(exchanges.router, prefix="/api")
app.include_router(stats.router, prefix="/api")

@app.get("/")
def root():
    return {"message": "SkillSwap API працює на SQLite!", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)