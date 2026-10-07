export const articleCategories = [
  "Food & Juices",
  "Nutrition Notes",
  "Supplements",
  "Mind & Mood",
  "Depression Journey",
  "Books & Quotes",
  "Stories & Reflections",
  "Daily Wisdom",
  "Spiritual / Inspirational Notes",
] as const;

export type ArticleCategory = (typeof articleCategories)[number];
