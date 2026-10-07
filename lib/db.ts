import mysql, { type Pool, type RowDataPacket } from "mysql2/promise";

const globalForMySql = globalThis as typeof globalThis & {
  notesFromMomPool?: Pool;
  notesFromMomSchema?: Promise<void>;
};

const createPostsTable = `
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
  ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
`;

function createPool(): Pool {
  const { DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME } = process.env;
  if (!DB_HOST || !DB_USER || DB_PASSWORD === undefined || !DB_NAME) {
    const missing = [];
    if (!DB_HOST) missing.push("DB_HOST");
    if (!DB_USER) missing.push("DB_USER");
    if (DB_PASSWORD === undefined) missing.push("DB_PASSWORD");
    if (!DB_NAME) missing.push("DB_NAME");
    throw new Error(`Missing MySQL configuration: ${missing.join(", ")}`);
  }

  const port = DB_PORT ? Number(DB_PORT) : 3306;
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("DB_PORT must be a valid TCP port.");
  }

  return mysql.createPool({
    host: DB_HOST,
    port,
    user: DB_USER,
    password: DB_PASSWORD,
    database: DB_NAME,
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0,
    charset: "utf8mb4",
  });
}

export function getPool(): Pool {
  if (!globalForMySql.notesFromMomPool) {
    globalForMySql.notesFromMomPool = createPool();
  }
  return globalForMySql.notesFromMomPool;
}

export function ensurePostsTable(): Promise<void> {
  if (!globalForMySql.notesFromMomSchema) {
    globalForMySql.notesFromMomSchema = getPool()
      .query(createPostsTable)
      .then(async () => {
        const [columns] = await getPool().query<
          (RowDataPacket & { DATA_TYPE: string })[]
        >(
          `SELECT DATA_TYPE
          FROM INFORMATION_SCHEMA.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'posts'
            AND COLUMN_NAME = 'category'`,
        );
        if (columns[0]?.DATA_TYPE.toLowerCase() === "enum") {
          await getPool().query(
            "ALTER TABLE posts MODIFY COLUMN category VARCHAR(64) NOT NULL DEFAULT 'Food & Juices'",
          );
        }
      })
      .then(() => undefined)
      .catch((error: unknown) => {
        globalForMySql.notesFromMomSchema = undefined;
        throw error;
      });
  }
  return globalForMySql.notesFromMomSchema;
}
