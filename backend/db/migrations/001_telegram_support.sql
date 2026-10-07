-- Apply once to an existing backend database before starting the updated app.
ALTER TABLE posts
    MODIFY COLUMN category_id INT NULL,
    ADD COLUMN telegram_file_id VARCHAR(255) NULL;

CREATE TABLE IF NOT EXISTS telegram_updates (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    update_id BIGINT NOT NULL,
    post_id INT NULL,
    processed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_telegram_updates_update_id UNIQUE (update_id),
    CONSTRAINT fk_telegram_updates_post
        FOREIGN KEY (post_id) REFERENCES posts (id) ON DELETE SET NULL
) ENGINE=InnoDB;
