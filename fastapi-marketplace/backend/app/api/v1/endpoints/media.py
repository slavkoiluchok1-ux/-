from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.media_handler import save_upload_file

router = APIRouter()

@router.post("/upload/photo")
async def upload_photo(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Файл повинен бути зображенням")
    url = await save_upload_file(file, folder="photos")
    return {"url": url}

@router.post("/upload/video")
async def upload_video(file: UploadFile = File(...)):
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Файл повинен бути відео")
    url = await save_upload_file(file, folder="videos")
    return {"url": url}
