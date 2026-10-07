"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { ArticleCard, formatArticleDate } from "@/components/article-card";
import { articleCategories } from "@/lib/article-categories";
import { useArticles } from "@/lib/use-articles";
import type { Article } from "@/lib/articles";

const filters = ["All", ...articleCategories] as const;

export default function ResourcesPage() {
  const { articles, dbNotice } = useArticles();
  const [activeCategory, setActiveCategory] =
    useState<(typeof filters)[number]>("All");
  const [search, setSearch] = useState("");
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null);
  const [newsletterMessage, setNewsletterMessage] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!selectedArticle) return;

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setSelectedArticle(null);
    }

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [selectedArticle]);

  const filteredArticles = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return articles.filter((article) => {
      const matchesCategory =
        activeCategory === "All" || article.category === activeCategory;
      const searchable = `${article.title} ${article.text} ${article.category}`.toLocaleLowerCase();
      return matchesCategory && searchable.includes(query);
    });
  }, [activeCategory, articles, search]);

  function handleNewsletter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNewsletterMessage("Thanks for being here — newsletter signup will be connected later.");
    event.currentTarget.reset();
  }

  return (
    <div className="min-h-screen">
      <header className="site-header">
        <Link className="brand" href="/" aria-label="Notes From Mom home">
          <span className="brand-mark" aria-hidden="true">n</span>
          <span>Notes From Mom</span>
        </Link>
        <button
          className="menu-toggle"
          type="button"
          aria-expanded={menuOpen}
          aria-controls="resources-nav"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span className="sr-only">Toggle navigation</span>
          <span />
          <span />
        </button>
        <nav
          className={`site-nav${menuOpen ? " is-open" : ""}`}
          id="resources-nav"
          aria-label="Main navigation"
        >
          <Link href="/#about" onClick={() => setMenuOpen(false)}>About</Link>
          <Link href="/resources" aria-current="page" onClick={() => setMenuOpen(false)}>Resources</Link>
          <Link href="/#contact" onClick={() => setMenuOpen(false)}>Contact</Link>
          <Link className="button button-small" href="/#newsletter-email" onClick={() => setMenuOpen(false)}>Get Started</Link>
        </nav>
      </header>

      <main className="resources-page">
        <section className="resources-intro content-wrap mx-auto">
          <span className="eyebrow">A little something for every day</span>
          <h1>All the good things, in one place.</h1>
          <p>Browse notes on nourishment, everyday life, and finding a little inspiration.</p>
        </section>

        <section className="resources-layout content-wrap mx-auto" aria-label="Browse articles">
          <aside className="category-sidebar" aria-label="Filter articles by category">
            <h2>Categories</h2>
            <div className="sidebar-category-list">
              {filters.map((category) => {
                const count =
                  category === "All"
                    ? articles.length
                    : articles.filter((article) => article.category === category).length;
                return (
                  <button
                    className={`sidebar-category${activeCategory === category ? " is-active" : ""}`}
                    type="button"
                    key={category}
                    aria-pressed={activeCategory === category}
                    onClick={() => setActiveCategory(category)}
                  >
                    <span>{category}</span>
                    <span className="category-count">{count}</span>
                  </button>
                );
              })}
            </div>
          </aside>

          <div className="resources-results">
            <div className="resources-toolbar">
              <div>
                <span className="eyebrow">Explore the notes</span>
                <h2>{activeCategory}</h2>
                <p>{filteredArticles.length} {filteredArticles.length === 1 ? "article" : "articles"}</p>
              </div>
              <label className="search-box">
                <span className="sr-only">Search articles</span>
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <circle cx="8.7" cy="8.7" r="5.6" />
                  <path d="m13 13 4 4" />
                </svg>
                <input
                  type="search"
                  placeholder="Search notes..."
                  autoComplete="off"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
            </div>

            {dbNotice && <p className="database-notice" role="status">{dbNotice}</p>}
            {filteredArticles.length === 0 ? (
              <p className="empty-results">No notes found in this category yet.</p>
            ) : (
              <div className="article-grid resources-grid" aria-live="polite">
                {filteredArticles.map((article) => (
                  <ArticleCard
                    article={article}
                    key={article.id}
                    onOpen={setSelectedArticle}
                  />
                ))}
              </div>
            )}
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <section className="newsletter content-wrap mx-auto" id="contact" aria-labelledby="newsletter-heading">
          <div className="newsletter-decoration" aria-hidden="true" />
          <div className="newsletter-copy">
            <span className="eyebrow eyebrow-light">A little goodness in your inbox</span>
            <h2 id="newsletter-heading">Let’s keep in touch.</h2>
            <p>Occasional notes with fresh ideas, favorite finds, and a little encouragement.</p>
            <form className="newsletter-form" onSubmit={handleNewsletter}>
              <label className="sr-only" htmlFor="newsletter-email">Your email address</label>
              <input id="newsletter-email" name="email" type="email" placeholder="Your email address" required />
              <button className="button button-white" type="submit">Count me in</button>
            </form>
            <p className="form-message" aria-live="polite">{newsletterMessage}</p>
            <small>No spam, ever. Just the good stuff.</small>
          </div>
        </section>
        <div className="footer-inner content-wrap mx-auto">
          <div className="footer-brand-column">
            <Link className="brand brand-footer" href="/">
              <span className="brand-mark" aria-hidden="true">n</span>
              <span>Notes From Mom</span>
            </Link>
            <p>A little reminder that the simple things are often the best things.</p>
          </div>
          <div className="footer-link-column">
            <h2>Explore</h2>
            <Link href="/#about">About me</Link>
            <Link href="/resources">All articles</Link>
            <Link href="/resources">Categories</Link>
          </div>
          <div className="footer-link-column">
            <h2>Resources</h2>
            <Link href="/resources">Latest articles</Link>
            <Link href="/resources">Browse categories</Link>
            <Link href="/#contact">Newsletter</Link>
          </div>
          <div className="footer-link-column">
            <h2>Say hello</h2>
            <Link href="/#contact">Get in touch</Link>
            <Link href="/">Back to top ↑</Link>
          </div>
          <div className="footer-bottom">
            <small>© {new Date().getFullYear()} Notes From Mom. Made with love, always.</small>
            <Link href="#">Back to top ↑</Link>
          </div>
        </div>
      </footer>

      {selectedArticle && (
        <div
          className="article-modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedArticle(null);
          }}
        >
          <article
            className="article-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
          >
            <button
              className="modal-close"
              type="button"
              aria-label="Close article"
              onClick={() => setSelectedArticle(null)}
            >
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="m4 4 8 8M12 4l-8 8" />
              </svg>
            </button>
            {selectedArticle.image && (
              <img className="modal-image" src={selectedArticle.image} alt="" />
            )}
            <div className="modal-copy">
              <span className="article-category">{selectedArticle.category}</span>
              <h2 id="modal-title">{selectedArticle.title}</h2>
              <div className="article-meta">
                <span className="avatar avatar-mom" aria-hidden="true">M</span>
                <span>Mom</span>
                <time dateTime={selectedArticle.date}>{formatArticleDate(selectedArticle.date)}</time>
              </div>
              <p className="modal-article-text">{selectedArticle.text}</p>
            </div>
          </article>
        </div>
      )}
    </div>
  );
}
