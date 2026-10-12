
import type { ArticleCategory } from "@/lib/article-categories";

export type PostType = "featured" | "latest" | "archive";

export type Article = {
  id: string;
  title: string;
  category: ArticleCategory | "Uncategorized";
  text: string;
  image: string | null;
  date: string;
  postType: PostType;
};
