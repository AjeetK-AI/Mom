import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import type { ResultSetHeader, RowDataPacket } from "mysql2";
import { ensurePostsTable, getPool } from "@/lib/db";
import { articleCategories, type ArticleCategory } from "@/lib/article-categories";

export const runtime = "nodejs";

type BackendPost = {
  id: number;
  title: string;
  content: string;
  category: { name: string } | null;
  featured_image_url: string | null;
  status: "draft" | "published" | "archived";
  published_at: string | null;
};

type BackendPostList = {
  items: BackendPost[];
};

type PostRow = RowDataPacket & {
  id: number;
  title: string;
  category: ArticleCategory;
  text: string;
  image: string;
  date: string;
};

function isArticleCategory(value: unknown): value is ArticleCategory {
  return articleCategories.some((category) => category === value);
}

function databaseError(error: unknown) {
  console.error("Notes From Mom database request failed.", error);
  const code =
    error && typeof error === "object" && "code" in error
      ? String(error.code)
      : "";
  const message =
    error instanceof Error && error.message.startsWith("Missing MySQL configuration")
      ? "MySQL is not configured. Set DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, and DB_NAME in .env.local."
      : code === "ER_BAD_DB_ERROR"
        ? "The configured MySQL database does not exist. Run db/schema.sql to create it."
        : code === "ER_ACCESS_DENIED_ERROR"
          ? "MySQL rejected the configured credentials. Check DB_USER and DB_PASSWORD."
          : code === "ECONNREFUSED" || code === "ENOTFOUND"
            ? "Could not connect to MySQL. Check DB_HOST, DB_PORT, and that the server is running."
            : code === "ER_BAD_FIELD_ERROR"
              ? "The posts table has an incompatible schema. Compare it with db/schema.sql."
              : "Unable to access posts. Check the MySQL connection and database schema.";
  return NextResponse.json(
    { error: message },
    { status: 503 },
  );
}

export async function GET() {
  try {
    const backendUrl = new URL(
      "/api/posts?limit=100",
      process.env.MOM_API_URL ?? "http://127.0.0.1:8000",
    );
    const response = await fetch(backendUrl, { cache: "no-store" });
    if (!response.ok) {
      console.error("Mom backend rejected a public article request.", response.status);
      return NextResponse.json(
        { error: "The Mom backend could not load published articles." },
        { status: 503 },
      );
    }

    const result = (await response.json()) as BackendPostList;
    if (!Array.isArray(result.items)) {
      throw new Error("Mom backend returned an invalid article list.");
    }
    const backendOrigin = backendUrl.origin;
    const posts = result.items
      .filter((post) => post.status === "published")
      .map((post) => ({
        id: String(post.id),
        title: post.title,
        category: post.category?.name ?? "Uncategorized",
        text: post.content,
        image: post.featured_image_url
          ? new URL(post.featured_image_url, backendOrigin).href
          : null,
        date: post.published_at?.slice(0, 10) ?? "",
      }));
    return NextResponse.json({ posts });
  } catch (error) {
    console.error("Mom backend article request failed.", error);
    return NextResponse.json(
      { error: "Published articles are unavailable. Check the Mom backend connection." },
      { status: 503 },
    );
  }
}

export async function POST(request: Request) {
  const adminToken = process.env.POSTS_ADMIN_TOKEN;
  if (!adminToken || Buffer.byteLength(adminToken) < 32) {
    return NextResponse.json(
      { error: "Publishing is not configured. Set a POSTS_ADMIN_TOKEN with at least 32 characters." },
      { status: 503 },
    );
  }

  const providedToken = request.headers.get("x-publish-token") ?? "";
  const providedTokenBytes = Buffer.from(providedToken);
  const adminTokenBytes = Buffer.from(adminToken);
  if (
    providedTokenBytes.length !== adminTokenBytes.length ||
    !timingSafeEqual(providedTokenBytes, adminTokenBytes)
  ) {
    return NextResponse.json({ error: "Enter the correct publishing key." }, { status: 401 });
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be valid JSON." }, { status: 400 });
  }

  if (!payload || typeof payload !== "object") {
    return NextResponse.json({ error: "Post details are required." }, { status: 400 });
  }

  const body = payload as Record<string, unknown>;
  const title = typeof body.title === "string" ? body.title.trim() : "";
  const text = typeof body.text === "string" ? body.text.trim() : "";
  const image = typeof body.image === "string" ? body.image.trim() : "";
  const category =
    body.category === undefined || body.category === null || body.category === ""
      ? "Food & Juices"
      : body.category;
  const date = body.date === undefined || body.date === null || body.date === "" ? null : body.date;

  if (!title || title.length > 120) {
    return NextResponse.json({ error: "Title is required and must be 120 characters or fewer." }, { status: 400 });
  }
  if (!text || text.length > 5000) {
    return NextResponse.json({ error: "Article text is required and must be 5,000 characters or fewer." }, { status: 400 });
  }
  if (!isArticleCategory(category)) {
    return NextResponse.json({ error: "Choose a valid category." }, { status: 400 });
  }

  let imageUrl: URL;
  try {
    imageUrl = new URL(image);
  } catch {
    return NextResponse.json({ error: "Enter a valid cover image URL." }, { status: 400 });
  }
  if (!["http:", "https:"].includes(imageUrl.protocol) || imageUrl.href.length > 2048) {
    return NextResponse.json({ error: "Cover image must be an HTTP or HTTPS URL under 2,048 characters." }, { status: 400 });
  }

  if (date !== null && (typeof date !== "string" || !isValidDate(date))) {
    return NextResponse.json({ error: "Date must use the YYYY-MM-DD format." }, { status: 400 });
  }

  try {
    await ensurePostsTable();
    const pool = getPool();
    const [result] = await pool.execute<ResultSetHeader>(
      "INSERT INTO posts (title, image_url, body, category, published_at) VALUES (?, ?, ?, ?, ?)",
      [title, imageUrl.href, text, category, date],
    );
    const postId = result.insertId;
    const [rows] = await pool.execute<PostRow[]>(
      `SELECT
        id,
        title,
        category,
        body AS text,
        image_url AS image,
        DATE_FORMAT(COALESCE(published_at, DATE(created_at)), '%Y-%m-%d') AS date
      FROM posts
      WHERE id = ?`,
      [postId],
    );

    if (!rows[0]) {
      throw new Error(`New post ${postId} was not returned after insert.`);
    }

    return NextResponse.json({ post: rows[0] }, { status: 201 });
  } catch (error) {
    return databaseError(error);
  }
}

function isValidDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
