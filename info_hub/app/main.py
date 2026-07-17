from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.routers.items import router 

app = FastAPI(
    title="InfoHub API",
    version="1.0.0",
    description="""
    API для роботи з товарами.

    Демонструє:
    - Pydantic
    - Swagger
    - Query
    - Dependency Injection
    - Тестування
    """,
    docs_url="/documentation",
    redoc_url="/redoc-docs"
)

app.include_router(router)

@app.get(
    "/custom-docs",
    response_class=HTMLResponse,
    tags=["Документація"]
)
def custom_docs():
    return """
    <html>
        <head>
            <title>InfoHub Docs</title>
        </head>
        <body>
            <h1>Власна документація</h1>
            <p>Навчальний FastAPI проєкт</p>
        </body>
    </html>
    """