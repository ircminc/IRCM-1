# 🏥 ANSI X12 Medical Billing Converter

A production-grade Streamlit application for processing HIPAA 5010 EDI files used in US healthcare revenue cycle management. Built for medical billing companies and healthcare providers.

---

## ✨ Features

### EDI Transaction Support
| TX Set | Name | Parse | Excel | PDF |
|--------|------|-------|-------|-----|
| **837P** | Professional Claims | ✅ | ✅ | ✅ |
| **835** | Electronic Remittance Advice | ✅ | ✅ | ✅ |
| **270** | Eligibility Inquiry | ✅ | ✅ | — |
| **271** | Eligibility Response | ✅ | ✅ | — |
| **276** | Claim Status Request | ✅ | ✅ | — |
| **277** | Claim Status Response | ✅ | ✅ | — |
| **834** | Benefit Enrollment | ✅ | ✅ | — |
| **820** | Payment Order | ✅ | ✅ | — |

### Revenue Cycle Analytics
- **KPI Dashboard** — Net Collection Rate, First Pass Resolution Rate, Days in A/R, Denial Rate with industry benchmark grading
- **AR Aging** — 0–30 / 31–60 / 61–90 / 90+ day aging buckets with trend charts
- **Denial Analytics** — CARC/RARC grouping, category breakdown, payer and CPT-level denial rates
- **Provider Performance** — Per-NPI revenue, collection rate, denial comparison
- **Underpayment Detection** — 835 vs CMS fee schedule variance analysis
- **Eligibility Analytics** — 270/271 coverage validation and success rates

### 🤖 Denial Intelligence
- **Pre-Submission Risk Scan** — Upload 837P and get risk scores per service line before submission
- Rule-based engine covering: missing NDC, unlisted procedures, modifier conflicts, diagnosis pointer issues, POS mismatches, J-code NDC requirements
- Historical enrichment from past 835 data
- Exportable risk report (Excel)

### 💊 CMS Rate Comparison
- Live PFS (Physician Fee Schedule) download from CMS — 19,000+ codes
- ASP (Average Sales Price) drug pricing — quarterly updates
- Rate flags: `OVER_300PCT` (compliance), `UNDER_100PCT` (underbilling), `WITHIN_RANGE`
- Automatic annual refresh via background scheduler

### 🔒 HIPAA-Conscious Security
- **File Encryption** — Fernet (AES-128) in-memory encryption with session-scoped keys
- **PHI Masking** — Names, DOB, IDs masked in displayed outputs and exports
- **No-Persistence Mode** — Process files without writing to database
- **Session Cleanup** — Secure temp file deletion on session end
- **Audit Logging** — JSON structured audit trail for all file operations

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Git

### Local Setup

```bash
# 1. Clone repository
git clone https://github.com/ircminc/IRCM-1.git
cd "IRCM-1"

# 2. Create virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# 5. Run the application
streamlit run app/main.py
```

The app opens at **http://localhost:8501**

### Windows Double-Click Launcher
```
run.bat
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and edit:

```env
# CMS rate thresholds
RATE_FLAG_OVER_PCT=300.0       # Flag if billed > 300% of Medicare rate
RATE_FLAG_UNDER_PCT=100.0      # Flag if billed < 100% of Medicare rate

# PFS conversion factor — update every January
PFS_CONVERSION_FACTOR=32.35    # CY2025

# HIPAA mode
HIPAA_MODE=false               # true = all protections enabled
HIPAA_MASK_PHI=false           # true = mask PHI in outputs only
HIPAA_NO_PERSISTENCE=false     # true = don't save to database
HIPAA_ENCRYPT_UPLOADS=false    # true = encrypt files in memory (requires: pip install cryptography)

# Logging
LOG_LEVEL=INFO                 # DEBUG | INFO | WARNING | ERROR
LOG_JSON=false                 # true = JSON structured logs

# Performance
BACKGROUND_PROCESSING_THRESHOLD_MB=10   # Files above this size use background threading
```

---

## 📁 Project Structure

```
ANSI X12 Tool/
├── app/                    # Application package (v2)
│   ├── main.py             # Streamlit entry point (streamlit run app/main.py)
│   ├── services/           # Business logic layer
│   │   ├── parse_service.py    # EDI parse orchestration + audit logging
│   │   ├── export_service.py   # Excel/PDF export orchestration
│   │   └── background.py       # Background threading for large files
│   ├── security/           # HIPAA security layer
│   │   ├── encryption.py       # Fernet file encryption
│   │   ├── phi_masker.py       # PHI field masking
│   │   ├── session_manager.py  # Session-scoped temp file lifecycle
│   │   └── audit_logger.py     # Structured JSON audit logging
│   └── utils/
│       └── logging_config.py   # Centralized logging setup
│
├── analytics/              # Analytics modules
│   ├── aggregator.py       # DataFrame queries from SQLite
│   ├── charts.py           # Plotly chart builders
│   ├── denial_analyzer.py  # CARC/RARC lookup and categorization
│   ├── trends.py           # Time-series trend analysis
│   ├── kpi_engine.py       # Revenue cycle KPIs (NCR, FPRR, DAR)
│   ├── underpayment.py     # 835 vs CMS fee schedule comparison
│   ├── provider_perf.py    # Per-NPI performance metrics
│   ├── eligibility_analytics.py  # 270/271 coverage analysis
│   └── denial_predictor.py # Rule-based denial prediction engine
│
├── core/                   # EDI parsing layer (HIPAA 5010)
│   ├── models/             # Pydantic domain models (837P, 835, 270–277, 834, 820)
│   └── parser/             # Transaction parsers + envelope + normalizer
│
├── cms_rates/              # CMS rate data
│   ├── pfs_client.py       # PFS RVU file downloader
│   ├── asp_client.py       # ASP drug pricing scraper
│   ├── rate_comparator.py  # Billed vs Medicare rate comparison
│   └── scheduler.py        # APScheduler auto-refresh jobs
│
├── exporters/              # Export layer
│   ├── excel/              # Multi-sheet Excel workbooks per TX type
│   └── pdf/                # ReportLab PDF reports
│
├── storage/                # Persistence layer
│   ├── database.py         # SQLAlchemy + SQLite (WAL mode)
│   ├── models_db.py        # ORM tables (ParsedFile, Claim837, etc.)
│   └── file_store.py       # save/list/delete file records
│
├── ui/pages/               # Streamlit pages
│   ├── 0_Home.py           # Landing page + quick stats
│   ├── 1_Upload_Parse.py   # File upload with background processing
│   ├── 2_Explorer.py       # Browse parsed data
│   ├── 3_Export.py         # Export to Excel/PDF
│   ├── 4_Analytics.py      # Denial analytics dashboard
│   ├── 5_CMS_Rates.py      # CMS rate lookup + 837P comparison
│   ├── 6_Settings.py       # Config + HIPAA + audit log
│   ├── 7_KPI_Dashboard.py  # RCM KPI dashboard
│   ├── 8_Provider_Performance.py  # Per-NPI analytics
│   └── 9_Denial_Intelligence.py   # Pre-submission risk + denial trends
│
├── tests/                  # Unit tests
│   ├── conftest.py         # pytest fixtures + sample EDI strings
│   ├── test_parsers.py     # Parser + parse service tests
│   └── test_analytics.py   # KPI, underpayment, predictor, PHI masker tests
│
├── app.py                  # Legacy entry point (backward compat → wraps app/main.py)
├── config.py               # Pydantic settings (reads from .env)
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Dev/test dependencies
├── .python-version         # Python 3.12
├── .streamlit/config.toml  # Streamlit server config
├── Dockerfile              # Container build
├── docker-compose.yml      # Local container run
└── .env.example            # Configuration template
```

---

## 🧪 Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific module
pytest tests/test_parsers.py -v
pytest tests/test_analytics.py -v
```

---

## 🐳 Docker Deployment

```bash
# Build image
docker build -t ansi-x12-billing .

# Run container
docker run -p 8501:8501 \
  -e RATE_FLAG_OVER_PCT=300 \
  -e PFS_CONVERSION_FACTOR=32.35 \
  -v billing_data:/app/data \
  ansi-x12-billing

# Or use docker-compose
docker-compose up
```

App available at **http://localhost:8501**

---

## ☁️ Streamlit Community Cloud Deployment

1. Push to GitHub: `https://github.com/ircminc/IRCM-1.git`
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Create new app:
   - **Repository:** `ircminc/IRCM-1`
   - **Branch:** `master`
   - **Main file:** `app/main.py`
   - **Python version:** `3.12`
4. Click **Deploy**

> **Note:** Streamlit Community Cloud uses ephemeral storage. Parsed files and the SQLite database reset on restart. For persistent production deployments, use Docker with a mounted volume or swap SQLite for PostgreSQL.

---

## 🔐 Security Notes

This application processes Protected Health Information (PHI) under HIPAA.

**Application-layer safeguards provided:**
- Optional Fernet encryption for in-memory file handling
- PHI masking in outputs (names, DOB, identifiers)
- Session-scoped temp file cleanup
- Structured audit logging of all file operations

**For HIPAA-compliant production hosting, additionally ensure:**
- HTTPS/TLS in transit (load balancer or reverse proxy)
- Disk encryption at rest (host OS level)
- Business Associate Agreement (BAA) with your cloud provider
- Access controls and user authentication (consider adding Streamlit authentication)
- Regular security reviews and penetration testing
- Formal risk analysis as required by HIPAA Security Rule §164.308(a)(1)

---

## 📄 License

Copyright © 2025 IRCM. All rights reserved.

---

## 🤝 Support

For issues or questions, contact the IRCM development team or open a GitHub issue at:
[https://github.com/ircminc/IRCM-1/issues](https://github.com/ircminc/IRCM-1/issues)
