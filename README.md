# XRIG Configurator AI

A PC build configurator and AI-powered chatbot that searches a Google Sheets database of quoted PC builds. Built for [XRIG Private Limited](https://xrig.com).

## Features

- **AI Chat** — Ask natural-language questions like *"Build me a PC within 1.5L with an RTX 4070"* and get real results from the database (powered by OpenAI GPT-4o).
- **Build Search** — Filter builds by budget, components, client name, quote ID, and date range.
- **File Upload** — Upload a `.csv` or `.txt` price list and the AI will cross-reference it.

## Architecture

| Component | Purpose |
|-----------|---------|
| `streamlit_app.py` | Streamlit Cloud web app (AI Chat + Build Search) |

## Deployment on Streamlit Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect your repo.
3. Set **Main file path** to `streamlit_app.py`.
4. In **Advanced settings → Secrets**, paste your secrets (see `secrets.toml.example`):
   - `OPENAI_API_KEY`
   - `[gcp_service_account]` — Google service account JSON for the configurator sheet
5. Deploy!

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Create local secrets
mkdir -p .streamlit
cp secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your real keys

# Run
streamlit run streamlit_app.py
```

## Security

- **Never commit credentials.** All API keys and service account files are in `.gitignore`.
- Secrets are managed via Streamlit's built-in secrets manager or environment variables.
- See `secrets.toml.example` for the expected format.
