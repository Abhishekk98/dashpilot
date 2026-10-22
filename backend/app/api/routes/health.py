import os
import platform
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    llm_provider: str
    llm_model: str
    llm_configured: bool


class SystemInfoResponse(BaseModel):
    app: str
    version: str
    python_version: str
    platform: str
    storage_dir: str
    max_upload_mb: int
    llm_provider: str
    llm_model: str
    llm_configured: bool
    llm_max_retries: int
    llm_timeout_seconds: int
    powerbi_desktop_installed: bool
    powerbi_desktop_path: str | None = None


def _check_pbi_desktop() -> tuple[bool, str | None]:
    standard_paths = [
        r"C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        r"C:\Program Files (x86)\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
    ]
    for p in standard_paths:
        if os.path.exists(p):
            return True, p
    return False, None


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness check used by the frontend footer status indicator."""
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.version,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        llm_configured=settings.llm_configured,
    )


@router.get("/system/info", response_model=SystemInfoResponse)
def system_info(settings: Settings = Depends(get_settings)) -> SystemInfoResponse:
    """Detailed system diagnostic and configuration information for the Settings page."""
    pbi_installed, pbi_path = _check_pbi_desktop()
    return SystemInfoResponse(
        app=settings.app_name,
        version=settings.version,
        python_version=platform.python_version(),
        platform=platform.platform(),
        storage_dir=str(settings.storage_dir),
        max_upload_mb=settings.max_upload_mb,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        llm_configured=settings.llm_configured,
        llm_max_retries=settings.llm_max_retries,
        llm_timeout_seconds=settings.llm_timeout_seconds,
        powerbi_desktop_installed=pbi_installed,
        powerbi_desktop_path=pbi_path,
    )
