# CiteCheck - Quick Start Guide

Get up and running in 5 minutes!

## Automated Setup (Recommended)

```bash
cd /home/mb/github/citecheck
./setup.sh
```

This script will:
- Create Python virtual environment
- Install all dependencies
- Guide you through database setup
- **Interactively configure .env file**
- Generate secure SECRET_KEY
- Prompt for Fastmail app password (securely hidden)
- Set up all configuration automatically

## Manual Setup (Alternative)

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Setup Database

```bash
# Install PostgreSQL if needed
sudo apt update && sudo apt install postgresql postgresql-contrib

# Initialize database
python backend/app/init_db.py
```

### 3. Configure Email

Edit `.env` and add your Fastmail app password:
```ini
SMTP_PASSWORD=your-actual-app-password
```

## Test It Out

### Quick Test (No Server Required)

Test the core PDF processing:

```bash
python test_processor.py "Sample_Briefs/Cause No. 01-24-00757-CR; Appellant's Opening Brief FILED.pdf"
```

This generates:
- `processed_brief.json` - Structured analysis
- `annotated_brief.pdf` - Color-coded PDF
- `citation_pairs.json` - Statement-citation pairs

### Run the API Server

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then visit: http://localhost:8000/docs

## API Quick Reference

### 1. Request Email Verification
```bash
curl -X POST http://localhost:8000/api/request-verification \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'
```

### 2. Verify Email (using token from email)
```bash
curl -X POST http://localhost:8000/api/verify-email \
  -H "Content-Type: application/json" \
  -d '{"token": "JWT_TOKEN_FROM_EMAIL"}'
```

### 3. Upload Brief
```bash
curl -X POST http://localhost:8000/api/upload-brief \
  -F "file=@path/to/brief.pdf" \
  -F "email=test@example.com"
```

### 4. Get Brief Data
```bash
curl http://localhost:8000/api/briefs/1
```

### 5. Download Annotated PDF
```bash
curl http://localhost:8000/api/briefs/1/download -o annotated.pdf
```

## Understanding the Output

### Color Coding (Annotated PDF)
- 🟢 **Green underline**: Statements (legal arguments/claims)
- 🔵 **Blue underline**: Quotations (case law, precedent)
- 🔴 **Red underline**: Citations (case/statute references)
- **Single underline**: Direct citation (no signal)
- **Double underline**: Signaled citation (see, cf., etc.)

### JSON Structure
```json
{
  "metadata": {
    "start_page": 55,
    "end_page": 84,
    "total_statements": 42,
    "total_quotations": 38,
    "total_citations": 89
  },
  "items": [
    {
      "text": "The evidence is legally insufficient...",
      "type": "statement",
      "citations": [
        {
          "text": "Baltimore v. State, 689 S.W.3d 331, 340",
          "type": "case",
          "signal": null,
          "pinpoint": "340",
          "is_signaled": false
        }
      ]
    }
  ]
}
```

## Troubleshooting

### Can't connect to database
```bash
sudo systemctl start postgresql
```

### Import errors
```bash
source venv/bin/activate  # Make sure venv is activated
pip install -r requirements.txt
```

### PDF not processing
- Ensure PDF has searchable text (not scanned image)
- Check that "Argument" and "Prayer" headings exist
- Try running test script to see detailed error

## Next Steps

1. **Test with your own briefs** - Try different legal brief formats
2. **Customize citation patterns** - Edit `citation_analyzer.py` for jurisdiction-specific formats
3. **Build the frontend** - React UI in `frontend/` directory
4. **Deploy to production** - See README.md for deployment guide

## Need Help?

- Full documentation: `README.md`
- API documentation: http://localhost:8000/docs (when server running)
- Contact: markwbennett@fastmail.com
