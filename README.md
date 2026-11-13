# Data Quality Inspector

Finds and fixes data-quality problems in banking datasets (Excel or CSV). Upload a messy file, review the suggested fixes, approve them, and download a cleaned Excel file with a report.

For the problem statement, components and workflow, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Features

- JWT login, each user sees only their own datasets
- Excel and CSV upload with a banking category and purpose
- Rule-based column mapping that remembers past choices
- Profiling and validation with Pandera, Great Expectations and custom Pandas rules
- Cleaning recommendations with a data-loss guard
- Human review: approve, reject or modify every action
- Cleaning with Python library tools (phonenumbers, email-validator, dateparser, price-parser, nameparser, rapidfuzz)
- Re-validation after cleaning with a before and after comparison
- Cleaned Excel file and an HTML report
- Optional local AI step (Qwen3:4b through Ollama and LangChain)

## Tech Stack

FastAPI, Streamlit, SQLite and SQLAlchemy, JWT (PyJWT, bcrypt), Pandas, NumPy, openpyxl, Pandera, Great Expectations, LangChain with Ollama (Qwen3:4b), phonenumbers, email-validator, dateparser, price-parser, nameparser, rapidfuzz.

## Prerequisites

- Python 3.10 or 3.11
- Git
- [Ollama](https://ollama.com), only if you want the AI step

## Installation

```bash
git clone https://github.com/<your-username>/DataQualityInspector.git
cd DataQualityInspector

python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root:

```dotenv
# Backend
SECRET_KEY=change-this-to-a-long-random-string
DATABASE_URL=sqlite:///./banking_cleaner.db
STORAGE_DIR=storage
CORS_ORIGINS=http://localhost:8501,http://localhost:3000

# AI step (optional)
LLM_ENABLED=false
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
LLM_TIMEOUT_SECONDS=120

# Optional engines
ENABLE_GREAT_EXPECTATIONS=true
ENABLE_YDATA=false

# Frontend
API_BASE_URL=http://127.0.0.1:8000
```

Never commit `.env`. Use a long random `SECRET_KEY`.

## Enable the AI Step (optional)

```bash
ollama pull qwen3:4b or ollama pull qwen3:1.7b
```

Set `LLM_ENABLED=true` in `.env`. Without it, recommendations come from the built-in rule table and every other step works the same. The first AI call is slow on a CPU-only machine, so allow a minute or two.

## Run

Open two terminals, activate the virtual environment in both.

**Terminal 1: backend**

```bash
uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`. Interactive API docs: `http://127.0.0.1:8000/docs`.

**Terminal 2: frontend**

```bash
streamlit run frontend/app.py
```

The app opens at `http://localhost:8501`. Start the backend first.

## How to Use

1. **Register and log in.**
2. **Upload** an Excel or CSV file. Choose the banking category and the purpose.
3. **Column mapping:** check each suggested mapping, fix wrong ones, and confirm.
4. **Analyze:** the system profiles the data and lists the issues it found.
5. **Recommendations:** each issue gets a suggested cleaning action.
6. **Review:** approve, reject or modify each action. Edit category mappings if needed (for example `Chk` to `Checking`). Read any data-loss warning before approving row deletions.
7. **Clean:** the approved actions run on the data.
8. **Download** the cleaned Excel file and open the HTML report.

To remove a dataset and its files, use the delete option on the upload page.

## Project Structure

```
DataQualityInspector/
├── app/                  # FastAPI backend
│   ├── main.py
│   ├── core/             # settings, security
│   ├── api/routes/       # auth.py, datasets.py
│   ├── models/
│   ├── schemas/
│   ├── database/
│   └── services/         # pipeline, validation, cleaning, report ...
├── frontend/             # Streamlit frontend
│   ├── app.py
│   ├── views/
│   └── services/api.py
├── storage/              # uploads, cleaned files, reports (not committed)
├── .env                  # not committed
├── requirements.txt
├── ARCHITECTURE.md
└── README.md
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Frontend shows a connection error | Start the backend first and check `API_BASE_URL` in `.env` |
| `NameError: BASE_URL` or `API_URL` in `frontend/services/api.py` | Make sure the URL variable is defined at the top of that file and used consistently |
| `AttributeError: no attribute 'delete_dataset'` | Add `delete_dataset` to `frontend/services/api.py` and the `DELETE /datasets/{id}` route to the backend |
| Analyze takes very long | Set `LLM_ENABLED=false`, keep `ENABLE_YDATA=false`, or set `ENABLE_GREAT_EXPECTATIONS=false` |
| Recommendations return a 500 error | Check the backend terminal for the traceback and make sure `build_recommendations` returns its result |
| Great Expectations or Pandera error | The run continues without that engine; the reason is shown in the results under `engine_notes` |
| Old results after changing code | Upload and analyze the file again so recommendations are rebuilt |

## Ignore These in Git

`.gitignore`:

```
venv/
__pycache__/
*.pyc
.env
*.db
storage/
```

## Author

Sankaranarayanan M