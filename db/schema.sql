CREATE DATABASE IF NOT EXISTS notes_from_mom
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE notes_from_mom;

CREATE TABLE IF NOT EXISTS posts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  title VARCHAR(120) NOT NULL,
  image_url VARCHAR(2048) NOT NULL,
  body TEXT NOT NULL,
  category VARCHAR(64) NOT NULL DEFAULT 'Food & Juices',
  published_at DATE NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  INDEX posts_created_at_idx (created_at),
  INDEX posts_category_idx (category)
);
