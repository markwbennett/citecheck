from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import os
import shutil
from pathlib import Path
import json

from .database import engine, get_db, Base
from .models import User, Brief
from .email_service import send_verification_email, verify_token
from .brief_processor import BriefProcessor
from .pdf_annotator import PDFAnnotator
from .config import get_settings

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="CiteCheck API", version="1.0.0")

settings = get_settings()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create upload directories
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
ANNOTATED_DIR = UPLOAD_DIR / "annotated"
ANNOTATED_DIR.mkdir(exist_ok=True)


# Pydantic models for request/response
class EmailRequest(BaseModel):
    email: EmailStr


class VerifyTokenRequest(BaseModel):
    token: str


class BriefResponse(BaseModel):
    id: int
    filename: str
    uploaded_at: str
    processed: bool
    argument_data: dict = None
    annotated_pdf_available: bool


@app.get("/")
async def root():
    return {"message": "CiteCheck API", "version": "1.0.0"}


@app.post("/api/request-verification")
async def request_verification(
    request: EmailRequest,
    db: Session = Depends(get_db)
):
    """
    Request email verification. If email doesn't exist in database,
    create user and send verification email.
    """
    # Check if user exists
    user = db.query(User).filter(User.email == request.email).first()

    if user:
        if user.is_verified:
            return {
                "message": "Email already verified",
                "verified": True,
                "user_id": user.id
            }
        else:
            # Resend verification email
            send_verification_email(request.email)
            return {
                "message": "Verification email resent",
                "verified": False
            }
    else:
        # Create new user
        user = User(email=request.email, is_verified=False)
        db.add(user)
        db.commit()
        db.refresh(user)

        # Send verification email
        try:
            send_verification_email(request.email)
            return {
                "message": "Verification email sent",
                "verified": False,
                "user_id": user.id
            }
        except Exception as e:
            db.delete(user)
            db.commit()
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/verify-email")
async def verify_email(
    request: VerifyTokenRequest,
    db: Session = Depends(get_db)
):
    """Verify email address using token from verification link."""
    try:
        email = verify_token(request.token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Find user and mark as verified
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_verified = True
    db.commit()

    return {
        "message": "Email verified successfully",
        "email": email,
        "user_id": user.id
    }


@app.post("/api/upload-brief")
async def upload_brief(
    file: UploadFile = File(...),
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Upload and process a legal brief PDF.
    User must be verified before uploading.
    """
    # Check if user exists and is verified
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified")

    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Save the uploaded file
    file_path = UPLOAD_DIR / f"{user.id}_{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Create brief record
    brief = Brief(
        user_id=user.id,
        filename=file.filename,
        original_pdf_path=str(file_path)
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)

    # Process the brief
    try:
        processor = BriefProcessor(str(file_path))
        processed_data = processor.process_brief()
        processor.close()

        # Generate annotated PDF
        annotated_path = ANNOTATED_DIR / f"{brief.id}_annotated.pdf"
        annotator = PDFAnnotator(str(file_path))
        annotator.annotate_brief(processed_data, str(annotated_path))
        annotator.close()

        # Update brief record
        brief.processed_at = db.query(Brief).filter(Brief.id == brief.id).first().uploaded_at
        brief.argument_data = processed_data
        brief.annotated_pdf_path = str(annotated_path)
        brief.argument_start_page = processed_data['metadata']['start_page']
        brief.argument_end_page = processed_data['metadata']['end_page']
        brief.total_statements = processed_data['metadata']['total_statements']
        brief.total_quotations = processed_data['metadata']['total_quotations']
        brief.total_citations = processed_data['metadata']['total_citations']
        db.commit()

        return {
            "message": "Brief processed successfully",
            "brief_id": brief.id,
            "metadata": processed_data['metadata']
        }

    except Exception as e:
        # Delete the brief record if processing fails
        db.delete(brief)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Error processing brief: {str(e)}")


@app.get("/api/briefs/{brief_id}")
async def get_brief(
    brief_id: int,
    db: Session = Depends(get_db)
):
    """Get details about a processed brief."""
    brief = db.query(Brief).filter(Brief.id == brief_id).first()

    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    return {
        "id": brief.id,
        "filename": brief.filename,
        "uploaded_at": brief.uploaded_at.isoformat(),
        "processed_at": brief.processed_at.isoformat() if brief.processed_at else None,
        "metadata": {
            "start_page": brief.argument_start_page,
            "end_page": brief.argument_end_page,
            "total_statements": brief.total_statements,
            "total_quotations": brief.total_quotations,
            "total_citations": brief.total_citations
        },
        "argument_data": brief.argument_data
    }


@app.get("/api/briefs/{brief_id}/download")
async def download_annotated_brief(
    brief_id: int,
    db: Session = Depends(get_db)
):
    """Download the annotated PDF."""
    brief = db.query(Brief).filter(Brief.id == brief_id).first()

    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    if not brief.annotated_pdf_path or not os.path.exists(brief.annotated_pdf_path):
        raise HTTPException(status_code=404, detail="Annotated PDF not found")

    return FileResponse(
        brief.annotated_pdf_path,
        media_type="application/pdf",
        filename=f"annotated_{brief.filename}"
    )


@app.get("/api/user/briefs")
async def get_user_briefs(
    email: str,
    db: Session = Depends(get_db)
):
    """Get all briefs for a user."""
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    briefs = db.query(Brief).filter(Brief.user_id == user.id).all()

    return {
        "email": user.email,
        "briefs": [
            {
                "id": brief.id,
                "filename": brief.filename,
                "uploaded_at": brief.uploaded_at.isoformat(),
                "processed": brief.processed_at is not None,
                "total_statements": brief.total_statements,
                "total_quotations": brief.total_quotations,
                "total_citations": brief.total_citations
            }
            for brief in briefs
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
