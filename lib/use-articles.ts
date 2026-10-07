"use client";

import { useEffect, useState } from "react";
import type { Article } from "@/lib/articles";

export function useArticles() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [dbNotice, setDbNotice] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/posts", { signal: controller.signal })
      .then(async (response) => {
        const result = (await response.json()) as {
          posts?: Article[];
          error?: string;
        };
        if (!response.ok) {
          throw new Error(result.error ?? "Could not load posts.");
        }
        return result.posts ?? [];
      })
      .then((posts) => {
        setArticles(posts);
        setDbNotice("");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const errorMessage = error instanceof Error ? error.message : "";
        setArticles([]);
        setDbNotice(
          `Published articles are unavailable. ${
            errorMessage || "Check that the Mom backend is running."
          }`,
        );
      });

    return () => controller.abort();
  }, []);

  return { articles, dbNotice };
}
