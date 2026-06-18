# GTM Content Studio

A small multi-agent system (LangChain + LangGraph) that turns a **product, feature, or upcoming event** into a full go-to-market content suite — **grounded in your own documents** via RAG.

It produces, ready to edit:
- a **LinkedIn post**
- a **promotional email** (subject + body)
- a **short blog draft**
- **3 ad copy variations** (different angles)

A separate **review agent** then critiques every piece for factual grounding, cross-format consistency, and tone — and loops content back for revision until it passes (or hits a revision cap).

## How it works

```
ingest docs ─▶ retrieve ─▶ strategist ─▶ generate ─▶ review
   (RAG)        (top-k)     (audience      (4 formats)   │
                            + tone)            ▲         │ needs revision
                                               └─────────┘  (loop, max N)
                                                            │ passed
                                                            ▼
                                                       final suite
```

- **retrieve** — embeds your `./data` docs into a FAISS store and pulls the top-k relevant chunks for the topic.
- **strategist** — reads that context, picks one primary audience, a tone, value props, key messages, and a single CTA.
- **generate** — writes all four formats, kept consistent with the strategy.
- **review** — scores the suite 1–10 and flags ungrounded claims or inconsistencies; if it fails, the graph routes back to `generate` with the critique attached.

Each agent returns **typed, structured output** (Pydantic), so the pieces stay clean and easy to render or post-process.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then fill in your key(s)
```

Pick a provider in `.env` 
- OpenAI for everything (one key, simplest).

## Run — Two Ways

### Option 1: CLI with Markdown Output

Generate content via command line. Output is printed to terminal **and** saved to `gtm_output.md`:

```bash
# With a topic argument
python gtm_agent.py "Sentinel AI launch"

# Or pass nothing to be prompted
python gtm_agent.py
```

**Output:** Terminal display + editable `gtm_output.md` file in project root.

Try the included sample data:
- `"VectorForge 2.0 Launch Webinar"`  (an event)
- `"PromptPilot CI gates"`             (a feature)
- `"InsightStream feature store"`      (a product)

### Option 2: Web UI

Generate content interactively via a modern web interface. Perfect for iterative refinement:

```bash
python app.py
# Then open http://127.0.0.1:5000 in your browser
```

**Features:**
- Interactive topic input with example buttons
- Real-time generation with progress indicators
- Strategy, content, review, and revision details all displayed
- Per-piece reviewer critiques
- User rating system for each piece
- Copy-to-clipboard for easy editing
- Beautiful responsive design

## Output Formats

### CLI Output (`gtm_agent.py`)
- **Terminal display**: Rich formatted output with panels and colors
- **File output**: `gtm_output.md` — ready-to-edit markdown with all pieces

### Web UI Output (`app.py`)
- **Interactive dashboard**: Real-time review scores, critiques, and revisions
- **Copy-to-clipboard**: Export any piece directly to clipboard
- **User ratings**: Rate each piece (stored in browser localStorage)
- **Review feedback**: See exactly what the review agent critiques

## Use your own docs

Drop files into `./data` — the agent ingests every `.pdf` and `.csv` it finds:
- **Product list / spec sheet** → PDF or CSV
- **Event calendar** → CSV
- **Google Sheet** → File ▸ Download ▸ CSV, then drop it in `./data`

Useful columns to include: launch dates, specs/features, target audience, pricing, and **past campaign messaging** (so new content matches your voice).

## Which Method Should I Use?

| Feature | CLI (`gtm_agent.py`) | Web UI (`app.py`) |
|---------|----------------------|-------------------|
| Output format | Terminal + `gtm_output.md` | Interactive web dashboard |
| Best for | Batch processing, automation, CI/CD | Iterative refinement, review loops |
| Revision workflow | Sequential, looped automatically | Visual feedback on each revision |
| Copy content | Manual selection from terminal/file | One-click copy-to-clipboard |
| Ratings/feedback | Command line only | Interactive star ratings |
| See review scores | End of process | Real-time dashboard |
| Perfect for | Scripts, pipelines | Human content review |

## Quick Start Examples

**Batch process a list of topics:**
```bash
for topic in "Product A Launch" "Feature B Release" "Event C"; do
  python gtm_agent.py "$topic"
  # Each creates gtm_output.md with full suite
done
```

**Refine a single topic interactively:**
```bash
python app.py
# Visit http://127.0.0.1:5000
# Try topics, see reviews, rate pieces, copy to clipboard
```

## Tune it

- **Revision strictness** — `max_revisions` in `main()` (default 2). The reviewer triggers a revision when score < 8 or any grounding/consistency check fails (see `REVIEW_PROMPT`).
- **Retrieval depth** — `k` in `build_retriever()`.
- **Creativity vs. precision** — the `temperature` passed to `get_llm()` per node (strategist 0.4, generate 0.8, review 0.3).
- **Formats / tone rules** — edit `GENERATE_PROMPT`.
- **Flask server settings** — Edit host/port/debug in `app.py` if needed.

## File Locations & Outputs

```
Project3/
├── app.py                    # Web UI server (Flask)
├── gtm_agent.py              # CLI & core agent logic
├── main.py                   # Alternative entry point
├── gtm_output.md             # Generated suite (CLI output) ← Check here after running gtm_agent.py
├── data/                     # Your source documents
│   ├── events.csv
│   └── products.csv
├── templates/
│   ├── index.html           # Web UI template
│   └── static/
│       ├── app.js           # Frontend logic
│       └── style.css        # Web UI styling
└── requirements.txt         # Dependencies
```

### Where to Find Generated Content:

**CLI Mode (`python gtm_agent.py`)**
- Terminal: Rich formatted output with all pieces
- File: `gtm_output.md` in project root (ready to copy/edit)

**Web Mode (`python app.py`)**
- Visit `http://127.0.0.1:5000` in browser
- All output displayed interactively on dashboard
- Click "Copy" buttons to export any piece

## Tests

The graph wiring and review loop are covered with a mocked LLM — no API key or network needed:

```bash
pip install pytest
pytest -q
```

Covers the happy path (no revision), a single revision then pass, and the max-revisions cap.

## Troubleshooting

**Flask app won't start?**
- Ensure Flask is installed: `pip install flask`
- Check port 5000 is free, or edit host/port in `app.py`
- Look at startup log messages for issues

**No content generated?**
- Check `.env` has valid API keys
- Verify `./data` has PDF or CSV files
- Try sample topics first: `"VectorForge 2.0 Launch Webinar"`

**"No PDF or CSV files found" error?**
- Add files to `./data/` folder
- Ensure they end in `.pdf` or `.csv` (case-insensitive)
- Supported formats: PDF (via pypdf) and CSV (via langchain-community)

**Review score too low?**
- Increase `max_revisions` for more iterations
- Add more detailed source documents
- Adjust `temperature` in `gtm_agent.py` for different creativity levels
