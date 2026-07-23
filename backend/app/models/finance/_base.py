from sqlalchemy import Column, DateTime, text
from sqlalchemy.sql import func

class TimestampMixin:
    created_at = Column(DateTime, default=func.now(), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), server_default=text("now()"), nullable=False)
