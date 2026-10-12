"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { ArticleCard, formatArticleDate } from "@/components/article-card";
import { articleCategories } from "@/lib/article-categories";
import { useArticles } from "@/lib/use-articles";
import type { Article } from "@/lib/articles";

export default function HomePage() {
  const { articles, dbNotice } = useArticles();
  const [activeCategory, setActiveCategory] = useState<string>("All");
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
  
  const featuredArticles = filteredArticles
    .filter((article) => article.postType === "featured")
    .slice(0, 3);

  const latestArticles = filteredArticles.filter(
    (article) => article.postType === "latest",
  );

  const archiveArticles = filteredArticles.filter(
    (article) => article.postType === "archive",
  );

  const articleRows = [
    {
      title: "Featured",
      description: "A few handpicked notes to bring a little goodness into your day.",
      articles: featuredArticles,
    },
    {
      title: "Latest",
      description: "Fresh thoughts and new favorites from the Notes From Mom journal.",
      articles: latestArticles,
    },
    {
      title: "From the Archive",
      description: "A few timeless notes to revisit whenever you need them.",
      articles: archiveArticles,
    },
  ];


  function handleNewsletter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNewsletterMessage("Thanks for being here — newsletter signup will be connected later.");
    event.currentTarget.reset();
  }

  return (
    <div className="min-h-screen">
      <header className="site-header">
        <a className="brand" href="#home" aria-label="Notes From Mom home">
          <span className="brand-mark" aria-hidden="true">n</span>
          <span>Notes From Mom</span>
        </a>
        <button
          className="menu-toggle"
          type="button"
          aria-expanded={menuOpen}
          aria-controls="site-nav"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span className="sr-only">Toggle navigation</span>
          <span />
          <span />
        </button>
        <nav
          className={`site-nav${menuOpen ? " is-open" : ""}`}
          id="site-nav"
          aria-label="Main navigation"
        >
          <a href="#about" onClick={() => setMenuOpen(false)}>About</a>
          <Link href="/resources" onClick={() => setMenuOpen(false)}>Resources</Link>
          <a href="#contact" onClick={() => setMenuOpen(false)}>Contact</a>
          <a className="button button-small" href="#newsletter-email" onClick={() => setMenuOpen(false)}>
            Get Started
          </a>
        </nav>
      </header>

      <main id="home" className="min-h-screen">
        <section className="intro section-wrap mx-auto w-full">
          <span className="eyebrow">A little note for you</span>
          <h1>Good things, shared<br className="desktop-break" /> from the heart.</h1>
          <p className="subtitle">
            Stories, memories, everyday thoughts, and things worth sharing from
            my little corner of the world. Take a moment, look around, and
            perhaps find something that speaks to you.
          </p>
        </section>

        <section className="about-feature content-wrap mx-auto" id="about" aria-labelledby="about-heading">
          <img
            className="feature-image"
            src="/about-coffee-book.png"
            alt="A cup of coffee resting on an open book beside a window"
          />
          <div className="feature-copy about">
            <span className="article-category">About me</span>
            <h2 id="about-heading">A little corner of my world.</h2>
            <p>
              I’m so glad you’re here. This is a collection of the things I’ve
              learned, loved, experienced, and found meaningful over the years —
              from thoughts on health and well-being to books, memories,
              reflections, and everyday wisdom.
            </p>
            <p>
              I hope you find something here that makes you think, inspires you,
              or simply makes your day a little brighter.
            </p>
            <div className="byline">
              <span className="avatar avatar-mom" aria-hidden="true">M</span>
              <span className="author-name">With love, Mom</span>
              <span className="byline-date note-label">A note for today</span>
            </div>
          </div>
        </section>

        <section className="articles-section content-wrap mx-auto" id="articles" aria-labelledby="articles-heading">
          <div className="section-heading">
            <span className="eyebrow">The good stuff</span>
            <h2 id="articles-heading">A little goodness for every day.</h2>
            <p>Thoughtful reads, warm reminders, and simple ideas to enjoy at your own pace.</p>
          </div>

          <div className="article-controls">
            <div className="category-tabs" role="group" aria-label="Filter articles by category">
              {["All", ...articleCategories].map((category) => (
                <button
                  className={`category-tab${activeCategory === category ? " is-active" : ""}`}
                  type="button"
                  key={category}
                  aria-pressed={activeCategory === category}
                  onClick={() => {
                    setActiveCategory(category);
                  }}
                >
                  {category}
                </button>
              ))}
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
                onChange={(event) => {
                  setSearch(event.target.value);
                }}
              />
            </label>
          </div>

          {dbNotice && <p className="database-notice" role="status">{dbNotice}</p>}
          {filteredArticles.length === 0 ? (
            <p className="empty-results">No notes found. Try another search or category.</p>
          ) : (
            <div aria-live="polite">
              {articleRows.map((row) => row.articles.length > 0 && (
                <section className="home-article-row" key={row.title} aria-labelledby={`row-${row.title.replaceAll(" ", "-").toLowerCase()}`}>
                  <div className="home-row-heading">
                    <h3 id={`row-${row.title.replaceAll(" ", "-").toLowerCase()}`}>{row.title}</h3>
                    <p>{row.description}</p>
                  </div>
                  <div className="article-grid">
                    {row.articles.map((article) => (
                      <ArticleCard
                        article={article}
                        key={article.id}
                        onOpen={setSelectedArticle}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
          <div className="view-all-wrap">
            <Link className="button view-all-button" href="/resources">
              View All Articles <span aria-hidden="true">→</span>
            </Link>
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
            <a className="brand brand-footer" href="#home">
              <span className="brand-mark" aria-hidden="true">n</span>
              <span>Notes From Mom</span>
            </a>
            <p>A little reminder that the simple things are often the best things.</p>
          </div>
          <div className="footer-link-column">
            <h2>Explore</h2>
            <a href="#about">About me</a>
            <Link href="/resources">All articles</Link>
            <Link href="/resources">Categories</Link>
          </div>
          <div className="footer-link-column">
            <h2>Resources</h2>
            <Link href="/resources">Latest articles</Link>
            <Link href="/resources">Browse categories</Link>
            <a href="#contact">Newsletter</a>
          </div>
          <div className="footer-link-column">
            <h2>Say hello</h2>
            <a href="#contact">Get in touch</a>
            <a href="#home">Back to top ↑</a>
          </div>
          <div className="footer-bottom">
            <small>© {new Date().getFullYear()} Notes From Mom. Made with love, always.</small>
            <a href="#home">Back to top ↑</a>
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
            
{selectedArticle.postType === "featured" && (
  <>
    {selectedArticle.image && (
      <img
        className="modal-image"
        src={selectedArticle.image}
        alt={selectedArticle.title}
      />
    )}

    <div className="modal-copy">
      <span className="article-category">
        {selectedArticle.category}
      </span>

      <h2 id="modal-title">{selectedArticle.title}</h2>

      <div className="article-meta">
        <span className="avatar avatar-mom" aria-hidden="true">M</span>
        <span>Mom</span>
        <time dateTime={selectedArticle.date}>
          {formatArticleDate(selectedArticle.date)}
        </time>
      </div>

      <p className="modal-article-text">{selectedArticle.text}</p>
    </div>
  </>
)}

{selectedArticle.postType === "latest" && (
  <div className="modal-copy">
    <p className="modal-article-text">{selectedArticle.text}</p>
  </div>
)}

{selectedArticle.postType === "archive" && selectedArticle.image && (
  <img
    className="modal-image archive-modal-image"
    src={selectedArticle.image}
    alt={selectedArticle.title}
  />
)}

          </article>
        </div>
      )}
    </div>
  );
}
