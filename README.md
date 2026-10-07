# Notes From Mom

A responsive Next.js, Tailwind CSS, and MySQL article site. The homepage shows up to nine notes; `/resources` lists all articles and filters them by category.

Categories: Food & Juices, Nutrition Notes, Supplements, Mind & Mood, Depression Journey, Books & Quotes, Stories & Reflections, Daily Wisdom, and Spiritual / Inspirational Notes. “All” shows posts across every category.

## Run locally

1. Install Node.js 20.9 or newer and MySQL.
2. Copy `.env.example` to `.env.local` with `cp .env.example .env.local`.
3. Edit `.env.local` and enter the host, port, username, password, and database name for your running MySQL server. Do not leave the example password in place.
4. Create the database by running `mysql -u root -p < db/schema.sql` and entering your MySQL password when prompted. If your MySQL username is not `root`, use an account that can create databases and tables.
5. Install dependencies with `npm install`.
6. Start the development server with `npm run dev`, then open `http://localhost:3000`. On this Mac, if the default shell still selects Node 18, use `PATH="/opt/homebrew/opt/node@22/bin:$PATH" npm run dev` instead.

Restart the development server after changing `.env.local`. The article API creates the `posts` table automatically once it can connect to the configured database and upgrades an older category enum to support all article categories. If the sample-notes message remains, check the server terminal for the database connection error, then verify that the MySQL server is running and the `.env.local` values match it. The public page continues to show starter content when MySQL is unavailable.

`POSTS_ADMIN_TOKEN` is only needed to enable API publishing; the public site does not expose a post-creation form. Use a private value with at least 32 characters. Keep `.env.local` private and do not commit it.

The cover image field accepts an HTTP or HTTPS image URL. Newsletter signup is currently a front-end placeholder.
