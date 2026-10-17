from fastapi import Depends

from app.config import Settings, get_settings
from core.projects import ProjectStore


def get_store(settings: Settings = Depends(get_settings)) -> ProjectStore:
    return ProjectStore(settings.storage_dir)
