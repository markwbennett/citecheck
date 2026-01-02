from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    briefs = relationship("Brief", back_populates="user")


class Brief(Base):
    __tablename__ = "briefs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    # Store the parsed argument section as JSON
    argument_data = Column(JSONB, nullable=True)

    # Store paths to original and annotated PDFs
    original_pdf_path = Column(String, nullable=False)
    annotated_pdf_path = Column(String, nullable=True)

    # Metadata
    argument_start_page = Column(Integer, nullable=True)
    argument_end_page = Column(Integer, nullable=True)
    total_statements = Column(Integer, default=0)
    total_quotations = Column(Integer, default=0)
    total_citations = Column(Integer, default=0)

    user = relationship("User", back_populates="briefs")
