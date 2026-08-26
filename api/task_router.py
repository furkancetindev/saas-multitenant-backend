from uuid import UUID # YENİ EKLENDİ
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from schemas.task import TaskUpdateDetail
from core.dependencies import get_current_user, get_task_service
from core.limiter import limiter
from schemas.task import TaskCreate, TaskResponse, TaskUpdate
from services.task_service import TaskService
from models.domain import User

router = APIRouter(prefix="/tasks", tags=["Görevler (Tasks)"])

@router.post("/", response_model=TaskResponse)
@limiter.limit("60/minute")  # Anahtar kimlik bazlı: bkz. core/limiter.py
def create_task(
    request: Request,  # slowapi dekoratörünün zorunlu kıldığı parametre
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service)
):
    try:
        return task_service.create_task(task_data, tenant_id=current_user.tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=list[TaskResponse])
def get_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100), # Güvenlik: Maksimum 100 kayıt çekilebilir
    current_user: User = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service)
):
    return task_service.get_tasks_by_tenant(current_user.tenant_id, skip=skip, limit=limit)

@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service)
):
    """
    Tek bir görevi getirir.

    Başka bir kiracının görev ID'si ile çağrıldığında 403 değil **404** döner:
    kaydın var olduğunu bile sızdırmıyoruz. Bu, projedeki hata sözleşmesinin
    en net görüldüğü endpoint.
    """
    task = task_service.get_task_by_id(str(task_id), current_user.tenant_id)
    if not task:
        raise HTTPException(status_code=404, detail="Görev bulunamadı!")
    return task

@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_task_status(
    task_id: UUID, # str yerine UUID yapıldı
    task_update: TaskUpdate,
    current_user: User = Depends(get_current_user),
    task_service: TaskService = Depends(get_task_service)
):
    # Servise gönderirken str() ile çeviriyoruz
    updated = task_service.update_task_status(str(task_id), current_user.tenant_id, task_update.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Görev bulunamadı veya bu işlem için yetkiniz yok.")
    return updated

@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
        task_id: UUID, # str yerine UUID yapıldı
        task_update: TaskUpdateDetail,
        current_user: User = Depends(get_current_user),
        task_service: TaskService = Depends(get_task_service)
):
    try:
        # Servise gönderirken str() ile çeviriyoruz
        updated = task_service.update_task_detail(str(task_id), current_user.tenant_id, task_update)
        if not updated:
            raise HTTPException(status_code=404, detail="Görev bulunamadı!")
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{task_id}", status_code=204)
def delete_task(
        task_id: UUID, # str yerine UUID yapıldı
        current_user: User = Depends(get_current_user),
        task_service: TaskService = Depends(get_task_service)
):
    # Servise gönderirken str() ile çeviriyoruz
    success = task_service.delete_task(str(task_id), current_user.tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Görev bulunamadı!")
    return None