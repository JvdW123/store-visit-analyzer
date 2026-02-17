# Store Visit Analyzer — Data Consolidation Tool

Consolidates messy supermarket shelf analysis Excel files into a single clean master dataset.

## Setup

```bash
# 1. Clone or download this project
# 2. Navigate to the project folder
cd store-visit-analyzer

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py
```

## Documentation

All project documentation is in `docs/`:

| Document | Content |
|----------|---------|
| `PRD.md` | Objectives, scope, user stories, UI flow |
| `SCHEMA.md` | Master column definitions, data types, valid values |
| `RULES.md` | Normalization rules, deterministic vs LLM logic |
| `ARCHITECTURE.md` | File structure, module responsibilities, data flow |
| `FILENAME_CONFIG.md` | Retailer/city/format parsing configuration |
| `TESTING.md` | Testing strategy, ground truth comparison |

## Testing

```bash
# Run unit tests
python -m pytest tests/ -v

# Run ground truth comparison (after ground truth file is created)
python tests/compare_ground_truth.py
```

## Project Structure

```
store-visit-analyzer/
├── app.py                  # Streamlit entry point
├── config/                 # Configuration (rules, mappings)
├── processing/             # Core processing pipeline
├── utils/                  # Shared utilities
├── docs/                   # Documentation
└── tests/                  # Tests + fixtures
```

See `docs/ARCHITECTURE.md` for detailed module descriptions.
