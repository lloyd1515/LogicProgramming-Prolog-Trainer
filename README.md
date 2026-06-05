# LogicProgramming-Prolog-Trainer

O aplicație web interactivă pentru pregătirea examenului de Programare Logică (Prolog) la UTCN.

## Funcționalități

- **Căutare semantică** în cursurile PDF (13 documente) + manualul Potolea
- **Asistent Q&A** bazat pe slide-uri, alimentat de Gemini AI
- **Mod Quiz Examen** cu 120 de întrebări oficiale extrase din examenele anterioare
- **Generator de întrebări noi** bazat pe conținutul cursurilor și few-shot prompting din baza de date

## Setup

### Cerințe

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

### Configurare API Key

Setează variabila de mediu `GEMINI_API_KEY` cu cheia ta Google Gemini API:

```powershell
# Windows PowerShell
$env:GEMINI_API_KEY = "AIzaSy..."

# Linux/macOS
export GEMINI_API_KEY="AIzaSy..."
```

Sau introdu cheia direct în sidebar-ul aplicației.

### Indexarea cursurilor

Copiază PDF-urile cursurilor în folderul `Curs/` (la rădăcina repo-ului), apoi rulează:

```bash
python app/index_courses.py
```

### Extragerea întrebărilor din quiz

Copiază screenshoturile și PDF-ul cu răspunsuri în `ExempleQuiz/` (la rădăcina repo-ului), apoi rulează:

```bash
python app/extract_everything.py
```

### Rularea aplicației

```bash
streamlit run app/app.py
```

Aplicația va fi disponibilă la `http://localhost:8501`.

### Căutare CLI (fără UI)

```bash
python app/search_cli.py "Ce este cut în Prolog?"
```

## Structura proiectului

```
app/
  app.py                 # Aplicația Streamlit principală
  index_courses.py       # Indexare PDF-uri în ChromaDB
  extract_everything.py  # Extragere întrebări din ExempleQuiz/
  search_cli.py          # CLI pentru căutare semantică
requirements.txt
README.md
Curs/                      # PDF-uri cursuri (neincluze în repo)
ExempleQuiz/               # Screenshoturi + PDF examen (neincluze în repo)
.env.example               # Template variabile de mediu
```

## Note

- `app/chroma_store/` și `app/quizzes.json` sunt generate local și **nu** sunt incluse în repo.
- Indexarea inițială poate dura câteva minute (descărcare model embeddings).
- Modelele Gemini disponibile: `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-flash`.
