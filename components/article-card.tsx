"use client";

import type { Article } from "@/lib/articles";

export function formatArticleDate(date: string) {
  const parsed = new Date(`${date}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return "Date not set";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

export function ArticleCard({
  article,
  onOpen,
}: {
  article: Article;
  onOpen: (article: Article) => void;
}) {
  const showImage =
    article.postType !== "latest" && article.image;

  return (
   <article className={`article-card article-card-${article.postType}`}>
    {showImage && (
      <div
        className={`article-image-wrap ${
          article.postType === "archive" ? "archive-image-only" : ""
        }`}
      >
        {article.postType === "archive" ? (
          <button
            type="button"
            className="archive-image-button"
            onClick={() => onOpen(article)}
            aria-label={`Open archive image: ${article.title}`}
          >
            <img
              className="article-image"
              src={article.image!}
              alt={article.title}
              loading="lazy"
            />
          </button>
        ) : (
          <img
            className="article-image"
            src={article.image!}
            alt={article.title}
            loading="lazy"
          />
        )}
      </div>
    )}

    {article.postType !== "archive" && (
      <>
        <span className="article-category">{article.category}</span>

        <h3>
          <button
            className="article-title"
            type="button"
            onClick={() => onOpen(article)}
          >
            {article.title}
          </button>
        </h3>

        <p className="article-excerpt">{article.text}</p>

        <div className="article-meta">
          <span className="avatar avatar-mom" aria-hidden="true">M</span>
          <span>Mom</span>
          <time dateTime={article.date}>
            {formatArticleDate(article.date)}
          </time>
        </div>
      </>
    )}
  </article>
  );
}
