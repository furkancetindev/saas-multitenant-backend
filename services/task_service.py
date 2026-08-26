from sqlalchemy.orm import Session
from repositories.task_repository import TaskRepository
from schemas.task import TaskCreate, TaskUpdateDetail
from models.domain import User  # Kullanıcı doğrulaması için eklendi


class TaskService:
    def __init__(self, db: Session):
        self.db = db  # Veritabanı oturumunu saklıyoruz
        self.repository = TaskRepository(db)

    def _validate_assignee(self, assigned_to_id: str, tenant_id: str):
        # Atanan kişi gerçekten bu şirkette mi çalışıyor?
        if assigned_to_id:
            user = self.db.query(User).filter(User.id == assigned_to_id, User.tenant_id == tenant_id).first()
            if not user:
                raise ValueError("Atanmak istenen kullanıcı bu şirkette bulunamadı!")

    def create_task(self, task_data: TaskCreate, tenant_id: str):
        self._validate_assignee(task_data.assigned_to, tenant_id)
        return self.repository.create_task(task_data, tenant_id)

    def get_task_by_id(self, task_id: str, tenant_id: str):
        return self.repository.get_task_by_id(task_id, tenant_id)

    def get_tasks_by_tenant(self, tenant_id: str, skip: int = 0, limit: int = 100):
        return self.repository.get_tasks_by_tenant(tenant_id, skip=skip, limit=limit)

    def update_task_status(self, task_id: str, tenant_id: str, new_status: str):
        return self.repository.update_task_status(task_id, tenant_id, new_status)

    def update_task_detail(self, task_id: str, tenant_id: str, task_update: TaskUpdateDetail):
        # Eğer güncellenen veride yeni bir kişiye atama varsa, onu da doğrula
        update_data = task_update.model_dump(exclude_unset=True)
        if "assigned_to" in update_data:
            self._validate_assignee(update_data["assigned_to"], tenant_id)

        return self.repository.update_task_detail(task_id, tenant_id, update_data)

    def delete_task(self, task_id: str, tenant_id: str):
        return self.repository.delete_task(task_id, tenant_id)