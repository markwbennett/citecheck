# CiteCheck - Legal Brief Analysis System

A web application that analyzes legal briefs, extracting the Argument section and identifying statements, quotations, and citations with intelligent pattern recognition.

## Features

- **Email Verification System**: Secure user registration with email confirmation
- **PDF Upload & Processing**: Upload legal brief PDFs for automated analysis
- **Argument Section Extraction**: Automatically identifies and extracts the Argument section (from "Argument" to "Prayer" headings)
- **Smart Citation Recognition**:
  - Case citations (e.g., "Baltimore v. State, 689 S.W.3d 331, 340 (Tex. Crim. App. 2024)")
  - Statute citations (e.g., "Tex. Penal Code § 7.02(a)(2)")
  - Citation signals (see, cf., e.g., etc.)
  - Pinpoint citations
  - String citations
  - "id." callbacks to previous citations
- **Content Classification**: Distinguishes between statements, quotations, and citations
- **Annotated PDF Generation**: Creates color-coded PDF with:
  - Green underline: Statements
  - Blue underline: Quotations
  - Red underline: Citations
  - Double underline: Signaled citations
  - Single underline: Direct citations
- **JSON Output**: Structured data pairing statements/quotations with their citations
- **PostgreSQL Storage**: Persistent storage of processed briefs and user data

## Technology Stack

- **Backend**: Python 3.9+ with FastAPI
- **Database**: PostgreSQL with JSONB support
- **PDF Processing**: PyMuPDF (fitz) and pdfplumber
- **Email**: SMTP (Fastmail configuration)
- **Frontend**: React (to be implemented)

## Project Structure

```
citecheck/
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── config.py              # Configuration and settings
│       ├── database.py            # Database connection
│       ├── models.py              # SQLAlchemy models
│       ├── main.py                # FastAPI application and endpoints
│       ├── pdf_extractor.py       # PDF text extraction
│       ├── citation_analyzer.py   # Citation pattern recognition
│       ├── brief_processor.py     # Main processing logic
│       ├── pdf_annotator.py       # PDF annotation with colored underlines
│       ├── email_service.py       # Email verification system
│       └── init_db.py             # Database initialization
├── frontend/                      # React frontend (to be implemented)
├── Sample_Briefs/                 # Sample PDF files for testing
├── test_processor.py              # Test script for core functionality
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## Setup Instructions

### Prerequisites

1. **Python 3.9 or higher**
   ```bash
   python3 --version
   ```

2. **PostgreSQL 12 or higher**
   ```bash
   # Install PostgreSQL (Ubuntu/Debian)
   sudo apt update
   sudo apt install postgresql postgresql-contrib

   # Start PostgreSQL service
   sudo systemctl start postgresql
   sudo systemctl enable postgresql
   ```

3. **Git** (if cloning from repository)

### Installation Steps

#### 1. Clone or Navigate to Project Directory

```bash
cd /home/mb/github/citecheck
```

#### 2. Create Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Set Up PostgreSQL Database

Run the database initialization script:

```bash
cd backend/app
python init_db.py
```

This will:
- Create the `citecheck` database
- Create the `citecheck_user` user with password `citecheck_password`
- Grant necessary privileges

**Note**: You'll need the PostgreSQL admin password when prompted.

#### 5. Configure Environment Variables

**Option A: Automatic (Recommended)**

The `setup.sh` script (step 1) handles this automatically:
- Generates a secure SECRET_KEY
- Prompts for your Fastmail app password (securely hidden input)
- Creates `.env` with all proper settings

**Option B: Manual**

If you skipped the setup script, copy and edit the example:

```bash
cp .env.example .env
nano .env  # Edit the file
```

**Important**: Replace `your-fastmail-app-password-here` with an actual Fastmail app-specific password.

To generate a Fastmail app password:
1. Log in to Fastmail
2. Go to Settings → Password & Security
3. Click "New App Password"
4. Name it "CiteCheck" and copy the generated password

## Running the Application

### Option 1: Test Core Functionality (No Web Server)

Test the PDF processing without running the full web application:

```bash
python test_processor.py "Sample_Briefs/Cause No. 01-24-00757-CR; Appellant's Opening Brief FILED.pdf"
```

This will:
- Extract and analyze the Argument section
- Generate `processed_brief.json` with structured data
- Create `annotated_brief.pdf` with colored underlines
- Generate `citation_pairs.json` with statement-citation pairs

### Option 2: Run the Full FastAPI Server

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at: `http://localhost:8000`

API Documentation (Swagger UI): `http://localhost:8000/docs`

### API Endpoints

#### POST `/api/request-verification`
Request email verification.
```json
{
  "email": "user@example.com"
}
```

#### POST `/api/verify-email`
Verify email with token from confirmation link.
```json
{
  "token": "jwt-token-from-email"
}
```

#### POST `/api/upload-brief`
Upload and process a PDF brief (requires verified email).
- Form data with `file` (PDF) and `email` fields

#### GET `/api/briefs/{brief_id}`
Get processed brief data including JSON analysis.

#### GET `/api/briefs/{brief_id}/download`
Download the annotated PDF.

#### GET `/api/user/briefs?email=user@example.com`
List all briefs for a user.

## Development

### Running Tests

```bash
# Test with sample brief
python test_processor.py "Sample_Briefs/Cause No. 01-24-00757-CR; Appellant's Opening Brief FILED.pdf"
```

### Database Management

Reset the database:
```bash
sudo -u postgres psql
DROP DATABASE citecheck;
DROP USER citecheck_user;
\q
python backend/app/init_db.py
```

View database contents:
```bash
sudo -u postgres psql -d citecheck
SELECT * FROM users;
SELECT * FROM briefs;
\q
```

### Frontend Development (To Be Implemented)

The React frontend will be located in the `frontend/` directory. It will include:
- Email input form
- Email verification page
- PDF upload interface
- Results display with annotated PDF viewer
- List of processed briefs

## Citation Pattern Examples

The system recognizes:

- **Case citations**: `Baltimore v. State, 689 S.W.3d 331, 340 (Tex. Crim. App. 2024)`
- **Statute citations**: `Tex. Penal Code § 7.02(a)(2)`
- **Signals**: `see`, `cf.`, `see also`, `e.g.`, `but see`, etc.
- **Id. citations**: `id.`, `id. at 340`
- **Pinpoint citations**: Page references after main citation
- **String citations**: Multiple citations separated by semicolons

## Troubleshooting

### PostgreSQL Connection Issues

```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Restart PostgreSQL
sudo systemctl restart postgresql
```

### Import Errors

Make sure you're in the virtual environment:
```bash
source venv/bin/activate
pip list  # Should show installed packages
```

### PDF Processing Errors

Ensure the PDF:
- Has searchable text (not just scanned images)
- Contains "Argument" and "Prayer" section headings
- Is a valid PDF file

## Production Deployment

For production deployment:

1. Change `SECRET_KEY` in `.env` to a secure random string
2. Update `FRONTEND_URL` to your production domain
3. Configure CORS in `backend/app/main.py` to allow only your frontend domain
4. Use a production WSGI server (already uses uvicorn)
5. Set up HTTPS/SSL certificates
6. Configure PostgreSQL for production (connection pooling, backups)
7. Set up file storage for uploaded PDFs (consider S3 or similar)

## License

© 2026 IACLS. All rights reserved.

## Support

For issues or questions, contact: markwbennett@fastmail.com
