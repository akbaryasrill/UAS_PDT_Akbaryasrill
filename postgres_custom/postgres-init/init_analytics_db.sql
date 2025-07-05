-- UAS-PDT/postgres_custom/postgres-init/init_analytics_db.sql
-- Inisialisasi untuk database analytics_db (PostgreSQL)

CREATE TABLE books_summary (
    book_id INT PRIMARY KEY,
    total_review INT DEFAULT 0,
    avg_rating NUMERIC(3,2) DEFAULT 0.0,
    total_borrowed INT DEFAULT 0
);

CREATE TABLE borrows_per_user (
    user_id INT PRIMARY KEY,
    user_name VARCHAR(255),
    total_borrows INT DEFAULT 0
);

CREATE TABLE late_returns (
    log_id INT PRIMARY KEY,
    book_id INT,
    user_id INT,
    borrowed_at TIMESTAMP WITH TIME ZONE,
    return_at TIMESTAMP WITH TIME ZONE,
    returned_at TIMESTAMP WITH TIME ZONE,
    late_days INT
);