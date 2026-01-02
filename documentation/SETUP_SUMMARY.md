# CiteCheck - Setup Summary

## 🎉 What's Been Built

A complete legal brief analysis system with:

### Core Features ✓
- ✅ PDF text extraction with page-spanning text handling
- ✅ Argument section extraction (from "Argument" to "Prayer")
- ✅ Citation pattern recognition (case law, statutes, signals, pinpoints, string cites, "id.")
- ✅ Content classification (statements, quotations, citations)
- ✅ JSON output with statement-citation pairing
- ✅ PDF annotation with colored underlines
- ✅ Email verification system
- ✅ PostgreSQL database with JSONB storage
- ✅ FastAPI REST API with full CRUD operations

### Project Structure

```
citecheck/
├── backend/app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app & endpoints
│   ├── config.py               # Settings & environment
│   ├── database.py             # Database connection
│   ├── models.py               # User & Brief models
│   ├── pdf_extractor.py        # PDF text extraction
│   ├── citation_analyzer.py    # Citation pattern recognition
│   ├── brief_processor.py      # Main processing logic
│   ├── pdf_annotator.py        # PDF color annotation
│   ├── email_service.py        # Email verification
│   └── init_db.py             # Database setup script
│
├── Sample_Briefs/              # Test PDFs
├── test_processor.py           # Standalone test script
├── setup.sh                    # Automated setup script
├── requirements.txt            # Python dependencies
├── README.md                   # Full documentation
├── QUICKSTART.md              # Quick start guide
└── .env.example               # Environment template
```

## 🚀 Quick Setup (2 Steps!)

### Step 1: Run Setup Script
```bash
cd /home/mb/github/citecheck
./setup.sh
```

This interactive script will:
- ✅ Create Python virtual environment
- ✅ Install all dependencies
- ✅ Set up PostgreSQL database
- ✅ **Generate secure SECRET_KEY automatically**
- ✅ **Prompt for Fastmail app password (securely)**
- ✅ **Create fully configured .env file**

**To get your Fastmail App Password** (have it ready):
1. Login to Fastmail
2. Settings → Password & Security
3. "New App Password"
4. Name it "CiteCheck"
5. Copy the password when setup script asks for it

### Step 2: Test It!
```bash
# Test core processing (no server needed)
python test_processor.py "Sample_Briefs/Cause No. 01-24-00757-CR; Appellant's Opening Brief FILED.pdf"

# Or start the API server
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 📊 What the System Does

### Input
Legal brief PDF with:
- "Argument" section heading
- "Prayer" section heading (marks end)
- Legal citations in standard format

### Output

1. **JSON Analysis** (`processed_brief.json`)
   - Structured breakdown of argument section
   - Each statement/quotation paired with citations
   - Metadata: page numbers, counts, etc.

2. **Annotated PDF** (`annotated_brief.pdf`)
   - Original PDF with color-coded underlines:
     - 🟢 Green = Statements
     - 🔵 Blue = Quotations
     - 🔴 Red = Citations
     - Single line = Direct cite
     - Double line = Signaled cite (see, cf., etc.)

3. **Citation Pairs** (`citation_pairs.json`)
   - Clean statement → citation mappings
   - Ready for further analysis

## 🔧 Configuration Details

### Database
- **Name**: `citecheck`
- **User**: `citecheck_user`
- **Password**: `citecheck_password`
- **Host**: `localhost:5432`

### Email (Fastmail)
- **SMTP**: `smtp.fastmail.com:587`
- **User**: `markwbennett@fastmail.com`
- **From**: `citecheck@iacls.org`
- **Verification**: 24-hour JWT tokens

### API Server
- **Default Port**: 8000
- **Documentation**: http://localhost:8000/docs
- **CORS**: Configured for all origins (change for production)

## 📝 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/request-verification` | Send verification email |
| POST | `/api/verify-email` | Verify email with token |
| POST | `/api/upload-brief` | Upload & process PDF |
| GET | `/api/briefs/{id}` | Get brief data & JSON |
| GET | `/api/briefs/{id}/download` | Download annotated PDF |
| GET | `/api/user/briefs?email=` | List user's briefs |

## 🧪 Testing

### Test Core Processing (Recommended First Step)
```bash
# Activate virtual environment
source venv/bin/activate

# Process sample brief
python test_processor.py "Sample_Briefs/Cause No. 01-24-00757-CR; Appellant's Opening Brief FILED.pdf"
```

**Expected Output:**
- Console output with statistics
- `processed_brief.json` - Full analysis
- `annotated_brief.pdf` - Color-coded PDF
- `citation_pairs.json` - Statement-citation pairs

### Test API Server
```bash
# Start server
cd backend
uvicorn app.main:app --reload

# In another terminal, test endpoint
curl http://localhost:8000/api/request-verification \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

## 🎯 Citation Patterns Recognized

The system identifies:

### Case Citations
```
Baltimore v. State, 689 S.W.3d 331, 340 (Tex. Crim. App. 2024)
Gross v. State, 380 S.W.3d 181, 186 (Tex. Crim. App. 2012)
```

### Statute Citations
```
Tex. Penal Code § 7.02(a)(2)
Art. 38.23
```

### Citation Signals
```
see, cf., see also, see generally, e.g., but see, contra, accord
```

### Special Citations
```
id.                  # References last citation
id. at 340          # With pinpoint reference
```

### Pinpoint Citations
```
, 340               # Page reference
at 186              # Alternate format
```

## 🔍 How It Works

1. **PDF Extraction** (`pdf_extractor.py`)
   - Extracts text with PyMuPDF
   - Handles page-spanning text
   - Finds section boundaries

2. **Citation Analysis** (`citation_analyzer.py`)
   - Regex patterns for citations
   - Signal detection
   - Quotation identification

3. **Processing** (`brief_processor.py`)
   - Splits into sentences
   - Classifies content type
   - Pairs statements with citations
   - Resolves "id." references

4. **Annotation** (`pdf_annotator.py`)
   - Adds colored underlines
   - Single/double lines for signals
   - Preserves original PDF

## 📚 Documentation

- **README.md** - Full documentation, troubleshooting, production deployment
- **QUICKSTART.md** - Fast setup guide with curl examples
- **SETUP_SUMMARY.md** - This file

## ⚠️ Important Notes

### Before First Use
1. **PostgreSQL must be running**: `sudo systemctl start postgresql`
2. **Database must be created**: Run `python backend/app/init_db.py`
3. **Email password must be set**: Edit `.env` file
4. **Virtual environment must be active**: `source venv/bin/activate`

### For Production Deployment
1. Change `SECRET_KEY` in `.env` to secure random value
2. Update CORS settings in `backend/app/main.py`
3. Use production database credentials
4. Set up SSL/HTTPS
5. Configure file upload limits
6. Set up backup system for database and PDFs

### Known Limitations
- Requires searchable PDF text (not scanned images)
- Assumes Texas legal citation format
- "Argument" and "Prayer" headings must exist
- Page-spanning text detection is heuristic-based

## 🎓 Next Steps

### Immediate
1. Test with sample brief
2. Verify email system works
3. Upload and process a real brief

### Short Term
1. Build React frontend in `frontend/` directory
2. Add user authentication (if needed beyond email verification)
3. Implement file upload limits and validation
4. Add error handling for edge cases

### Long Term
1. Support multiple jurisdiction citation formats
2. Add OCR for scanned PDFs
3. Machine learning for improved citation recognition
4. Batch processing for multiple briefs
5. Citation checking against databases
6. Export to Word/other formats

## 💬 Support

- **Email**: markwbennett@fastmail.com
- **API Docs**: http://localhost:8000/docs (when server running)
- **Sample Brief**: Located in `Sample_Briefs/` for testing

---

**Status**: ✅ Backend complete and ready for testing
**Next**: Configure email password and run first test
