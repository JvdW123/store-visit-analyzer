# Streamlit Configuration

This directory contains Streamlit-specific configuration files.

## Files

### `secrets.toml` (NOT in version control)
Contains sensitive credentials and passwords. **Never commit this file!**

To set up:
1. Copy `secrets.toml.example` to `secrets.toml`
2. Fill in your actual values
3. The file is already in `.gitignore` to prevent accidental commits

### `secrets.toml.example`
Template showing the required secrets format. Safe to commit to version control.

## Deployment to Streamlit Cloud

When deploying to Streamlit Cloud, you don't need to create a `secrets.toml` file. Instead:

1. Go to your app dashboard on Streamlit Cloud
2. Click on your app → "Settings" → "Secrets"
3. Add your secrets in TOML format:

```toml
APP_PASSWORD = "your-production-password"
ANTHROPIC_API_KEY = "sk-ant-api03-your-key-here"
```

4. Click "Save"

The app will automatically restart with the new secrets.

## Local Development

For local development:

1. Copy `secrets.toml.example` to `secrets.toml`
2. Set a simple password or comment out `APP_PASSWORD` to disable protection
3. Add your Anthropic API key
4. Run: `streamlit run app.py`

Example `secrets.toml` for local dev:
```toml
# Comment out to disable password protection locally
# APP_PASSWORD = "dev"

ANTHROPIC_API_KEY = "sk-ant-api03-your-actual-key"
```
