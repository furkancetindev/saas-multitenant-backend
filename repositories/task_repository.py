from sqlalchemy.orm import Session
from models.domain import Task
from schemas.task import TaskCreate


class TaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_task(self, task_data: TaskCreate, tenant_id: str):
        task_dict = task_data.model_dump()
        yeni_gorev = Task(**task_dict, tenant_id=tenant_id)
        self.db.add(yeni_gorev)
        self.db.commit()
        self.db.refresh(yeni_gorev)
        return yeni_gorev

    def get_task_by_id(self, task_id: str, tenant_id: str):
        # tenant_id filtresi burada bir yetki kontrolü değil, sorgunun kendisidir:
        # başka kiracının kaydı hiç dönmez, dolayısıyla router 404 verir.
        return (
            self.db.query(Task)
            .filter(Task.id == task_id, Task.tenant_id == tenant_id)
            .first()
        )

    def get_tasks_by_tenant(self, tenant_id: str, skip: int = 0, limit: int = 100):
        return self.db.query(Task).filter(Task.tenant_id == tenant_id).offset(skip).limit(limit).all()


    def update_task_status(self, task_id: str,tenant_id: str, new_status: str):
        task =  self.db.query(Task).filter(Task.id == task_id, Task.tenant_id == tenant_id).first()
        if task:
            task.status = new_status
            self.db.commit()
            self.db.refresh(task)
        return task

    def update_task_detail(self, task_id: str, tenant_id: str, update_data: dict):
        task = self.db.query(Task).filter(Task.id == task_id, Task.tenant_id == tenant_id).first()
        if task:
            for key, value in update_data.items():
                if value is not None:
                    setattr(task, key, value)
            self.db.commit()
            self.db.refresh(task)
        return task

    def delete_task(self, task_id: str, tenant_id: str) -> bool:
        task = self.db.query(Task).filter(Task.id == task_id, Task.tenant_id == tenant_id).first()
        if task:
            self.db.delete(task)
            self.db.commit()
            return True
        return False