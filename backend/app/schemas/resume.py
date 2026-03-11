from __future__ import annotations

from pydantic import BaseModel


class ResumeStatus(BaseModel):
    profile: str
    exists: bool = False
    filename: str = ""
    file_size: int = 0
    path: str = ""


class ResumeUploadResponse(BaseModel):
    profile: str
    filename: str
    message: str = "Resume uploaded successfully"
