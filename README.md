# FMI Codes Website

A modern, scalable Flask application for managing teams, mentors, rankings, and regulations for the FMI Codes competition.

## 🚀 Quick Start for New Machines

### Prerequisites
- **Python** 3.8+
- **Node.js** 16+ (for Prettier formatting hooks)
- **Git**

### Setup (5 minutes)

```bash
# 1. Clone the repository
git clone <repository-url>
cd fmi-codes-website

# 2. Create Python virtual environment
python -m venv .venv

# 3. Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Install Node.js dependencies (for code formatting)
npm install

# 6. Initialize Git hooks
npx husky install

# 7. Start the development server
python run_server.py
```

The app will be available at **http://localhost:5000**

---

## 📋 Project Architecture

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | Flask 3.0 | Web framework & API |
| **Database** | SQLite | Data persistence |
| **Frontend** | HTML/CSS/JavaScript | User interface |
| **Formatting** | Prettier | Code style consistency |
| **Hooks** | Husky + lint-staged | Pre-commit formatting |
| **Environment** | Python 3.8+ | Runtime |

### Application Structure

```
fmi-codes-website/
├── app/                          # Main application package
│   ├── __init__.py              # App factory pattern
│   ├── database.py              # DB initialization & utilities
│   ├── models/                  # Database models (ready for ORM)
│   ├── routes/                  # Route handlers (blueprints)
│   │   ├── auth.py             # Login, registration, session
│   │   ├── teams.py            # Team management CRUD
│   │   ├── mentors.py          # Mentor management & selection
│   │   ├── pages.py            # Static page serving
│   │   ├── api_routes.py       # API endpoints
│   │   └── api/                # Sub-API routes (scalable)
│   ├── services/                # Business logic layer
│   │   ├── team_service.py     # Team operations
│   │   ├── mentor_service.py   # Mentor operations
│   │   ├── mentor_selection_service.py
│   │   ├── ranking_service.py
│   │   └── regulations_service.py
│   ├── templates/               # HTML templates (organized by feature)
│   │   ├── auth/               # Login, registration pages
│   │   ├── mentors/            # Mentor management pages
│   │   ├── teams/              # Team management pages
│   │   ├── rankings/           # Ranking pages
│   │   └── *.html              # Base pages (home, etc)
│   ├── static/                  # Static assets
│   │   ├── images/
│   │   ├── companyLogos/
│   │   └── mentorPictures/
│   └── utils/                   # Utility functions (decorators, helpers)
│
├── config.py                     # Configuration management
├── run_server.py                 # Entry point
├── requirements.txt              # Python dependencies
├── package.json                  # Node.js dependencies
│
├── database/                     # Database utilities
│   ├── migrations/              # Schema version control
│   └── seeds/                   # Seed data (JSON files)
│
├── tests/                        # Test suite
│   ├── test_auth.py
│   ├── test_mentors.py
│   └── test_teams.py
│
├── .env.example                  # Environment variables template
├── .prettierrc                   # Code formatting config
├── .prettierignore              # Files to exclude from formatting
├── .git/hooks/pre-commit        # Auto-format on commit
├── .gitignore                   # Git ignore rules
└── README.md                    # This file
```

---

## 🏗️ Architecture Layers

### Separation of Concerns

```
┌─────────────────────────────────────────┐
│          HTTP Requests (Client)         │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│    Routes Layer (app/routes/*.py)       │  ← Handles HTTP
│  - Receive requests                     │
│  - Validate input                       │
│  - Call services                        │
│  - Return JSON/HTML responses           │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│   Services Layer (app/services/*.py)    │  ← Business Logic
│  - Team management                      │
│  - Mentor selection                     │
│  - Data validation                      │
│  - Complex operations                   │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│    Database Layer (app/database.py)    │  ← Data Access
│  - SQLite connection                    │
│  - Query execution                      │
│  - Schema management                    │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         SQLite Database                 │
│     (website.db)                        │
└─────────────────────────────────────────┘
```

### Data Flow Example: Team Registration

```
1. Client submits registration form
   ↓
2. Route Handler (routes/teams.py)
   - Receives JSON data
   - Calls team_service.register_team()
   ↓
3. Service Layer (services/team_service.py)
   - Validates input (3-6 participants)
   - Checks if team already exists
   - Orchestrates participant insertion
   ↓
4. Database Layer (app/database.py)
   - Executes SQL INSERT
   - Returns success/error
   ↓
5. Service returns result to Route
   ↓
6. Route sends JSON response to Client
```

---

## 💾 Database Schema

### Tables Overview

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| `teams` | Team registration | `id`, `team_name`, `password`, `participant_count` |
| `participants` | Team members | `id`, `team_id`, `first_name`, `last_name`, `faculty_number`, `discord` |
| `mentors` | Mentor profiles | `id`, `name`, `surname`, `workplace`, `picture`, `picture_filename` |
| `team_mentors` | Mentor assignments | `id`, `team_id`, `mentor_id` (capacity: 3 teams max per mentor) |

---

## 🎯 Development Workflow

### Code Style & Formatting

**Prettier automatically formats your code on every commit!**

#### Pre-commit Hook Workflow

```
git commit -m "Add feature"
  ↓
pre-commit hook runs
  ↓
Prettier formats staged files
  ↓
lint-staged re-stages formatted changes
  ↓
Commit completes successfully
```

#### Manual Formatting

```bash
# Format all eligible files
npm run format

# Check formatting without changes
npm run format:check
```

#### Prettier Configuration

**File:** `.prettierrc`
- **Print width:** 100 characters
- **Tab width:** 2 spaces
- **Quotes:** Single (for JS/JSON, HTML handled separately)
- **Trailing commas:** ES5 style
- **Line endings:** LF (Unix)

**Files formatted:**
- `.html` - HTML templates
- `.js` - JavaScript
- `.json` - JSON data
- `.css` - Stylesheets
- `.md` - Markdown

**Files excluded:** (see `.prettierignore`)
- Python files (use Black separately)
- Databases and builds
- Dependencies

---

## 🔧 Configuration

### Environment Variables

Create a `.env` file (copy from `.env.example`):

```bash
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-secret-key-here
DATABASE_PATH=website.db
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

### App Configuration

**File:** `config.py`

- **Development:** Debug mode on, auto-reload
- **Production:** Debug off, secure defaults
- **Testing:** In-memory DB, test fixtures

---

## 📦 Dependencies

### Python (requirements.txt)

```
Flask==3.0.0
```

Minimal by design—add as needed (SQLAlchemy for ORM, pytest for testing, etc.)

### Node.js (package.json)

```json
{
  "prettier": "^3.2.5",    // Code formatter
  "husky": "^9.0.11",      // Git hooks
  "lint-staged": "^15.2.2" // Run linters on staged files
}
```

---

## 🚦 Running the Application

### Development

```bash
python run_server.py
```

- Auto-reload on code changes
- Debug toolbar available at `http://localhost:5000/_debug`
- Full error messages and stack traces

### Production

```bash
# Using Gunicorn (production WSGI server)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## 🧪 Testing

### Running Tests

```bash
# Install pytest
pip install pytest

# Run all tests
pytest

# Run with coverage
pytest --cov=app
```

### Test Structure

```
tests/
├── test_auth.py       # Login, registration, sessions
├── test_teams.py      # Team CRUD operations
└── test_mentors.py    # Mentor management & selection
```

---

## 🤝 Contributing

### For Team Members

1. **Clone & Setup** (follow Quick Start above)
2. **Create a branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make changes** (code is auto-formatted on commit)
4. **Commit:**
   ```bash
   git commit -m "feat: add new feature"
   ```
5. **Push & create Pull Request:**
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Convention

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `refactor:` Code restructuring
- `test:` Test additions
- `chore:` Maintenance

Example:
```bash
git commit -m "feat: add mentor selection validation"
```

### Code Organization Guidelines

| Layer | Responsibility | Location |
|-------|-----------------|----------|
| **Routes** | HTTP handling | `app/routes/*.py` |
| **Services** | Business logic | `app/services/*.py` |
| **Database** | Data access | `app/database.py` |
| **Templates** | HTML rendering | `app/templates/**/*.html` |
| **Static** | CSS, images | `app/static/**` |

---

## 🔍 Troubleshooting

### Pre-commit Hook Not Running

```bash
# Verify hook is executable
ls -la .git/hooks/pre-commit

# Make it executable if needed
chmod +x .git/hooks/pre-commit

# Reinstall hooks
npx husky install
```

### Node.js Not Found

```bash
# Check installation
node --version
npm --version

# Install from https://nodejs.org (LTS recommended)
```

### Database Issues

```bash
# Reset database (deletes data!)
rm website.db

# Restart server (auto-creates new DB)
python run_server.py
```

### Import Errors

```bash
# Ensure virtual environment is activated
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux

# Reinstall dependencies
pip install -r requirements.txt
```

---

## 📚 API Documentation

### Authentication

**POST** `/api/login`
```json
{"teamName": "Team A", "password": "secret"}
```

**POST** `/api/logout`

**GET** `/api/session`

### Teams

**POST** `/api/register` - Register new team
**GET** `/api/teams` - List all teams
**GET** `/api/teams/<team_name>` - Get team details
**DELETE** `/api/teams/<team_name>` - Delete team

### Mentors

**GET** `/api/mentors` - List all mentors
**POST** `/api/mentors` - Register mentor
**GET** `/api/mentors/<id>/picture` - Get mentor photo
**POST** `/api/chooseMentor` - Select mentors for team

### Data

**GET** `/api/ranking` - Get rankings
**GET** `/api/regulations` - Get regulations

---

## 📞 Support

For issues or questions:
1. Check this README
2. Review code comments
3. Check git history: `git log --oneline`
4. Ask the team lead

---

## 📄 License

Internal project for FMI Codes competition.
