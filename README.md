# ArchaeoCode

AI-powered codebase archaeology — reconstructs architecture timelines, ownership evolution,
dependency history, and dead-code signals from a repo's git history.

## Install

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Usage

Index a repo's git history into SQLite:

```bash
archaeocode analyze /path/to/repo --db archaeocode.db
```

Then explore what it found:

```bash
archaeocode ownership --db archaeocode.db --top 15   # likely-dead / orphaned files
archaeocode deps /path/to/repo --file src/foo.py     # what imports a file
archaeocode blast /path/to/repo --file src/foo.py    # blast radius of changing a file
archaeocode verdict /path/to/repo --db archaeocode.db --top 20
archaeocode timeline --db archaeocode.db             # architecture timeline
archaeocode deleted --db archaeocode.db --min-days 30
archaeocode why src/foo.py --db archaeocode.db       # commit history + intent for a file
archaeocode intent --db archaeocode.db               # NLP-classified commit intents
```

## Requirements

- Python >= 3.10
- GitPython, SQLAlchemy, rich (see `requirements.txt`)
