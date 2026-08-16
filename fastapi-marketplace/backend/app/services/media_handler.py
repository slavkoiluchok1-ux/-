import os
import uuid
from fastapi import UploadFile

UPLOAD_DIR = "uploads"

async def save_upload_file(file: UploadFile, folder: str = "photos") -> str:
    target_dir = os.path.join(UPLOAD_DIR, folder)
    os.makedirs(target_dir, exist_ok=True)
    
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(target_dir, unique_filename)
    
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
        
    return f"/uploads/{folder}/{unique_filename}"
