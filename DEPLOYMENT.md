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
   git remote add origin https://github.com/Daksh-Saksena/GoogleChat_bot
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

## 6. Google Drive image clipping

The user token needs the `https://www.googleapis.com/auth/drive.readonly` scope to copy images attached as Google Drive files. After updating the bot, rerun `auth.py`, approve the additional permission, and replace `GOOGLE_USER_TOKEN_JSON` (or the `token.json` Secret File) with the newly generated token. The bot can then copy both Drive-backed images and images uploaded directly to Google Chat, including supported GIF attachments. The Google account used for this token must also have access to each attached Drive image.

Clip requests run on a dedicated background worker so normal Chat polling and replies continue while a clip is prepared. Large clips are split into ordered Highlights messages below Chat's message-size limit, and image attachments are distributed across those messages. Google Chat's 200 MB per-file upload limit still applies.

An explicit count in a clip request is no longer capped; without a count, the bot clips the most recent eligible message. To clip one specific message, reply to it with `Sonny clip this`; its text and attached images/GIFs are copied to Highlights. Large counts are limited by the history available in the source space.

## 7. Conversation Context

When replying to a mention or a direct reply to one of its messages, the bot uses up to the 20 most recent messages in the source space as working context. Direct replies in a bot-authored thread or quoted replies to a bot message trigger a response without requiring a name or keyword. The bot quotes the message it is answering and does not start or reply in a thread. It prioritizes messages from the same explicit Google Chat thread for context, and can infer a likely follow-up from the recent conversation even when the new message is not a formal reply. Each sender is labeled by their Google Chat account identity so people with the same display name are kept distinct.

For an unthreaded message that appears to continue an earlier exchange, the bot uses that exchange as context and quotes the new message in its response. Conversation context is fetched from Google Chat when needed; no separate conversation-history file is stored.

AI persona replies are kept short by default, usually one or two sentences. The bot uses a paragraph of up to 60 words only when the conversation needs more explanation, and may occasionally send a few separate short chat messages when that feels natural.

Start a message with `Sonny useful` to use the general-assistant mode instead of a persona. It can search the web with the OpenAI Responses web-search tool, search locally through the latest 1,000 messages returned by the Google Chat API, and perform supported actions when explicitly requested (post a quoted message, create a poll, clip recent messages to highlights, or summarize recent chat). Chat history is ranked locally because the Google Chat messages API does not provide full-text search. This mode requires a model and OpenAI account that support the Responses API web-search tool.

Say `Sonny Ram` to activate a high-intensity satirical tech-CEO persona. Activation posts the bundled `a6Dr0X9_460s.jpg` image with the single reply `GIMME THE RAM`; keep the image in the repository root when deploying. While active, Sonny mentions and messages mentioning the whole word `Ram` receive replies in that persona. Say `Sonny no ram` to restore the default Lucy persona; Sonny replies `ram altman disabled`. `Sonny clip that` still clips recent messages, copying both images uploaded directly to Google Chat and image attachments stored in Google Drive into Highlights.
