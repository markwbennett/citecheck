# CiteCheck - Command Cheat Sheet

## Setup (One Time)

```bash
# Complete automated setup (2 minutes)
./setup.sh

# Manual setup alternative
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python backend/app/init_db.py
```

## Test Core Functionality (No Server)

```bash
# Activate environment
source venv/bin/activate

# Process a brief
python test_processor.py "path/to/brief.pdf"

# Output files:
# - processed_brief.json    (structured analysis)
# - annotated_brief.pdf     (color-coded PDF)
# - citation_pairs.json     (statement-citation pairs)
```

## Run API Server

```bash
source venv/bin/activate
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Access docs at: http://localhost:8000/docs
```

## API Quick Reference

### 1. Request Verification Email
```bash
curl -X POST http://localhost:8000/api/request-verification \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

### 2. Verify Email
```bash
curl -X POST http://localhost:8000/api/verify-email \
  -H "Content-Type: application/json" \
  -d '{"token": "JWT_TOKEN"}'
```

### 3. Upload Brief
```bash
curl -X POST http://localhost:8000/api/upload-brief \
  -F "file=@brief.pdf" \
  -F "email=user@example.com"
```

### 4. Get Brief Data
```bash
curl http://localhost:8000/api/briefs/1 | jq
```

### 5. Download Annotated PDF
```bash
curl http://localhost:8000/api/briefs/1/download -o annotated.pdf
```

### 6. List User Briefs
```bash
curl "http://localhost:8000/api/user/briefs?email=user@example.com" | jq
```

## Database Management

```bash
# View database
sudo -u postgres psql -d citecheck

# Inside psql:
\dt                    # List tables
SELECT * FROM users;   # View users
SELECT * FROM briefs;  # View briefs
\q                     # Quit

# Reset database
sudo -u postgres psql
DROP DATABASE citecheck;
DROP USER citecheck_user;
\q
python backend/app/init_db.py
```

## Configuration

```bash
# View configuration
cat .env

# Edit configuration
nano .env

# Reconfigure (runs interactive setup)
./setup.sh
```

## Troubleshooting

```bash
# PostgreSQL not running
sudo systemctl start postgresql
sudo systemctl status postgresql

# Reinstall dependencies
source venv/bin/activate
pip install -r requirements.txt --force-reinstall

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
```

## File Locations

- **Backend code**: `backend/app/`
- **Uploaded PDFs**: `uploads/`
- **Annotated PDFs**: `uploads/annotated/`
- **Config**: `.env`
- **Logs**: Server console output

## Color Coding (Annotated PDFs)

- 🟢 **Green** = Statements
- 🔵 **Blue** = Quotations
- 🔴 **Red** = Citations
- **Single underline** = Direct citation
- **Double underline** = Signaled citation (see, cf., etc.)

## Citation Verification (Downstream Processing)

- **Quotations** → Direct text search in cited case
- **Statements** → AI semantic search in cited case
- **Mixed (quote + statement)** → **BOTH** direct search AND AI search
- **Parentheticals** → Extract from (holding that...) in signaled citations
- **`needs_review: true`** → Signaled citation missing parenthetical

**Key Rule:** If sentence has quotations, always perform BOTH searches.

See `CITATION_VERIFICATION_WORKFLOW.md` for detailed examples.

## Common Patterns

### Test → Deploy Workflow
```bash
# 1. Test locally
python test_processor.py "brief.pdf"

# 2. Start server
cd backend && uvicorn app.main:app --reload

# 3. Test API
curl http://localhost:8000/api/request-verification ...
```

### Development Workflow
```bash
# Always activate venv first
source venv/bin/activate

# Make code changes in backend/app/

# Server auto-reloads with --reload flag

# Test changes
curl http://localhost:8000/...
```

## Documentation

- `README.md` - Complete documentation
- `QUICKSTART.md` - Quick start guide
- `SETUP_SUMMARY.md` - Setup overview
- `CHEATSHEET.md` - This file
- http://localhost:8000/docs - API docs (when server running)
