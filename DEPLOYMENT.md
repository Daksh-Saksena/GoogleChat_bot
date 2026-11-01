# Tarkin Gupta (SummaryBot) - Cloud Deployment Guide (Render)

This repository is set up to run continuously as a **Background Worker** on [Render](https://render.com).

---

## 1. Local Files & Safety

The following files contain private tokens and credentials and **are excluded from Git** via `.gitignore`:
- `token.json` (User OAuth credentials for reading Google Chat)
- `bot_token.json` (Tarkin Gupta bot OAuth credentials for posting)
- `credentials.json`
- `.env`

---

## 2. Push to GitHub / GitLab

1. Initialize a git repository if you haven't already:
   ```bash
   git init
   git add .
   git commit -m "Configure Tarkin Gupta bot for Render background worker"
   ```
2. Create a **Private** repository on GitHub or GitLab and push your code:
   ```bash
   git remote add origin <YOUR_REPO_URL>
   git branch -M main
   git push -u origin main
   ```

---

## 3. Create Background Worker on Render

1. Log into your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** > **Background Worker**.
3. Connect your repository.
4. Configure service settings:
   - **Name**: `tarkin-gupta-summarybot` (or your preferred name)
   - **Region**: Select your preferred region (e.g. Frankfurt, Oregon, Singapore)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     python summarize_chat.py
     ```

---

## 4. Environment Variables on Render

In the **Environment** tab of your Render service, add the following variables:

| Variable Name | Value | Description |
|---|---|---|
| `OPENAI_API_KEY` | `sk-...` | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4.1-mini` | The OpenAI model to use |
| `GOOGLE_USER_TOKEN_JSON` | `{"token": ...}` | Complete JSON contents of your local `token.json` |
| `GOOGLE_BOT_TOKEN_JSON` | `{"token": ...}` | Complete JSON contents of your local `bot_token.json` |

*(Optional)* You can also configure:
- `SOURCE_SPACE`: `spaces/AAQAwjqNQNY` (defaults to this if omitted)
- `DESTINATION_SPACE`: `spaces/AAQAZRUbksc` (defaults to this if omitted)
- `POLL_INTERVAL`: `5` (seconds between polls)

---

## 5. Alternative: Render Secret Files

Instead of setting `GOOGLE_USER_TOKEN_JSON` and `GOOGLE_BOT_TOKEN_JSON` environment variables, Render also supports **Secret Files**:
1. In your Render service, navigate to **Environment** > **Secret Files**.
2. Add filename `token.json` and paste the contents of your local `token.json`.
3. Add filename `bot_token.json` and paste the contents of your local `bot_token.json`.
`summarize_chat.py` will automatically detect and load from them.

