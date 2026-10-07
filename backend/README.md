# Notes From Mom API

FastAPI and MySQL backend for the Notes From Mom website. Mom publishes directly from Telegram: send article text or a captioned photo, choose a category when prompted, and the backend publishes the article immediately. No LLM, admin panel, or paid image storage is used.

## Requirements and local run

- Python 3.12 or newer
- MySQL 8 or compatible MySQL server

The `app` package is inside `backend/`, so run Uvicorn from that directory (or use `--app-dir backend` from the parent folder). The module target must include the FastAPI object as `app.main:app`.

From the repository's `backend/` directory:

1. Create and activate a virtual environment:

   ```sh
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```sh
   pip install -r requirements.txt
   ```

3. Create a dedicated database:

   ```sql
   CREATE DATABASE notes_from_mom_backend
     CHARACTER SET utf8mb4
     COLLATE utf8mb4_unicode_ci;
   ```

   Use a dedicated least-privilege database account in production.

4. Create local configuration:

   ```sh
   cp .env.example .env
   ```

   Set `DATABASE_URL` to the MySQL connection string. Fill in Telegram values as described in [Telegram setup](#telegram-setup). `.env` is git-ignored. Never commit or share it.

5. Start the local server:

   ```sh
   uvicorn app.main:app --reload
   ```

   Uvicorn listens on port 8000 by default. The Next.js app uses port 3000. Open Swagger at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) or ReDoc at [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc).

Alternatively, from the parent `Mom/` directory, use:

```sh
backend/.venv/bin/uvicorn --app-dir backend --env-file backend/.env app.main:app --reload
```

The explicit `--env-file` is needed from the parent because settings otherwise look for `.env` in the current working directory. If you see `Could not import module "app.main"`, check that you are using the correct virtual environment, app directory, and environment-file path. The `:app` suffix is required.

At startup SQLAlchemy creates missing tables and the example categories. `create_all()` does not alter existing tables. For an existing backend database, stop the server and apply the one-time migration before starting the updated app:

```sh
mysql -u YOUR_DB_USER -p notes_from_mom_backend < db/migrations/001_telegram_support.sql
```

The migration makes `posts.category_id` nullable for Telegram drafts, adds `posts.telegram_file_id`, and creates `telegram_updates`. For a brand-new database, the current models create these structures automatically; do not run the one-time migration a second time against an already-created `posts` table.

Keep this backend on its dedicated database. The Next.js app’s separate `posts` table has a different schema.

## Article and category API

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `GET` | `/api/categories` | List categories |
| `GET` | `/api/posts?page=1&limit=12&category=education` | List **published** articles with pagination and optional category slug |
| `GET` | `/api/posts/{slug}` | Get one published article by slug |
| `GET` | `/uploads/{filename}` | Serve an image downloaded from Telegram |
| `POST` | `/api/posts` | Create an article |
| `PUT` | `/api/posts/{id}` | Update an article |
| `DELETE` | `/api/posts/{id}` | Delete an article |

List pagination returns:

```json
{
  "items": [],
  "page": 1,
  "limit": 12,
  "total": 0,
  "pages": 0
}
```

Public reads continue to show published posts only. Telegram submissions are drafts only while waiting for a category; drafts are not returned by `GET /api/posts`.

Example REST create request:

```json
{
  "title": "Every Child Deserves Education",
  "slug": "every-child-deserves-education",
  "content": "Full article...",
  "summary": "A reflection on education.",
  "category_id": 2,
  "featured_image_url": "https://example.com/education.jpg",
  "status": "draft"
}
```

Use a category ID returned by `GET /api/categories`; IDs vary by database. REST writes currently do not have admin authentication. Keep the API on a trusted local network and add admin authentication before public exposure.

## Telegram workflow and security

Set these environment variables in `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_ALLOWED_USER_ID=
```

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | BotFather-issued token used only by the Telegram service |
| `TELEGRAM_WEBHOOK_SECRET` | Random secret sent by Telegram in its webhook header |
| `TELEGRAM_ALLOWED_USER_ID` | The one numeric Telegram account ID allowed to publish articles |

The webhook is `POST /api/telegram/webhook`. It checks `X-Telegram-Bot-Api-Secret-Token` using a constant-time comparison, then checks the message sender against `TELEGRAM_ALLOWED_USER_ID` **before any database write**. Missing or incorrect secrets and other Telegram senders are rejected. Do not put tokens or secrets in source control, shell history, URLs you share, screenshots, or logs.

Supported messages:

- `/start` and `/help`: explain how to submit and publish an article. Other commands show the help message.
- Text: saved exactly as the article content with title `New Article`.
- Photo or image file with caption: caption is saved exactly as the article content, Telegram's largest photo or image document `file_id` is saved in `posts.telegram_file_id`, and the image is downloaded to `backend/uploads/`. Its `/uploads/...` path is saved in `posts.featured_image_url`.
- After a submission, Mom chooses Food & Juices, Nutrition Notes, Supplements, Mind & Mood, Depression Journey, Books & Quotes, Stories & Reflections, Daily Wisdom, or Spiritual / Inspirational Notes by name or number. Category-name matching is case-insensitive. The selected category is assigned and the post is immediately published.
- Empty text or a photo without a caption: the bot asks Mom to send article text or a caption; no post is created.
- Only one Telegram article can wait for a category at a time.

Each handled Telegram `update_id` is unique in `telegram_updates`. The update record and new draft, or the category response and publication, are committed in one database transaction. A duplicate update never creates a second post; retries can resend the appropriate category prompt or publication confirmation. Telegram API failures do not reveal response details or the token.

Webhook confirmations look like:

```text
Published successfully! ✅

Title: New Article
Category: Stories & Reflections
Post ID: 15
Status: published
```

If confirmation delivery fails after the database commit, the webhook returns a temporary error so Telegram can retry. A retry finds the existing update and resends the category prompt or confirmation without duplicating the post.

Images are stored locally in `backend/uploads/` and served through `/uploads/...`. The directory is excluded from source control. Local storage is suitable for development and persistent disks; use durable storage if deploying to infrastructure with ephemeral filesystems.

## Telegram setup

1. In Telegram, open **@BotFather**, send `/newbot`, follow its prompts, and save the returned bot token directly in the ignored local `.env` as `TELEGRAM_BOT_TOKEN`. Do not paste the token into code or this chat.
2. Find Mom's numeric account ID using a reputable Telegram ID bot such as **@userinfobot**: open it, send `/start`, and use the numeric user ID it reports for `TELEGRAM_ALLOWED_USER_ID`. Verify that ID belongs to Mom before configuring it.
3. Generate a long random webhook secret containing only letters, numbers, `_`, and `-`, then set it as `TELEGRAM_WEBHOOK_SECRET`. Keep the same value for the webhook registration.
4. Run FastAPI locally:

   ```sh
   uvicorn app.main:app --reload
   ```

5. Telegram cannot reach localhost. Expose port 8000 using one tunnel:

   ```sh
   ngrok http 8000
   ```

   Or:

   ```sh
   cloudflared tunnel --url http://localhost:8000
   ```

   Use the HTTPS forwarding URL printed by the tool. A temporary tunnel URL may change when restarted.

6. In a separate terminal, enter the bot token and webhook secret at hidden prompts (so neither value is saved in shell history), then register the webhook (replace the tunnel URL):

   ```sh
   printf "Bot token: "
   read -s TELEGRAM_BOT_TOKEN
   printf "\nWebhook secret: "
   read -s TELEGRAM_WEBHOOK_SECRET
   printf "\n"
   export TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET
   curl --fail-with-body -X POST \
     "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
     --data-urlencode "url=https://YOUR-TUNNEL-URL/api/telegram/webhook" \
     --data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}"
   unset TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET
   ```

   Telegram should return `{"ok":true,"result":true,...}`. The token is necessarily part of the Telegram Bot API URL; keep the command private and never log/share it.

7. Open the bot Mom created, press **Start** (or send `/start`), and send a plain-text article or a photo with a caption. Reply with a category name or number to publish it.

To check the current webhook status, use `getWebhookInfo` with the same token, keeping its URL private:

```text
https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```

## Verify a Telegram article in MySQL

Public `GET /api/posts` returns published articles only. To verify recent Telegram articles:

```sql
SELECT id, title, slug, content, category_id, featured_image_url,
       telegram_file_id, status, published_at
FROM posts
WHERE telegram_file_id IS NOT NULL OR slug LIKE 'new-article-%'
ORDER BY id DESC
LIMIT 10;
```

For a photo article, `featured_image_url` points to the local image and `telegram_file_id` retains Telegram's original file ID. Image bytes are not stored in MySQL.

## Tests

From `backend/`, run:

```sh
pytest -q
```

The automated tests use in-memory SQLite and mocked Telegram HTTP responses; they do not need a real database, tunnel, or bot token.

## Website connection

The Next.js website loads its public article list from the FastAPI `/api/posts` endpoint through its `/api/posts` proxy. Set `MOM_API_URL` in the website's `.env.local` to the backend origin (for example, `http://127.0.0.1:8000`). The backend public API filters out drafts; local images are served from the backend `/uploads/` route.
