ALTER TABLE posts
ADD COLUMN post_type ENUM('featured', 'latest', 'archive')
NOT NULL DEFAULT 'latest';
