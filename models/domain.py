from sqlalchemy import Column, String, ForeignKey, DateTime, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy import Boolean

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name= Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    users = relationship("User", back_populates="tenant")
    tasks = relationship("Task", back_populates="tenant")

class User(Base):
    __tablename__ = "users"

    # server_default şart: ORM dışında (düz SQL, veri aktarımı) eklenen satırlarda
    # NULL kalırsa get_current_user o kullanıcıyı kalıcı olarak 403'e kilitler.
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)
    id = Column(UUID(as_uuid=True),primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="user")
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    tenant = relationship("Tenant", back_populates="users")
    assigned_tasks = relationship("Task", back_populates="assigned_user")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True),primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default = "todo")
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id",ondelete = "SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))

    tenant = relationship("Tenant", back_populates="tasks")
    assigned_user = relationship("User", back_populates="assigned_tasks")



