from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.upload import router as upload_router
from app.api.invoices import router as invoices_router
from app.services.job_registry import get_registry

app = FastAPI(title="Invoice Extractor AI")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

app.include_router(upload_router)
app.include_router(invoices_router)


@app.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    registry = get_registry()
    jobs = registry.get_all_jobs()
    return templates.TemplateResponse("upload.html", {"request": request, "jobs": jobs})
