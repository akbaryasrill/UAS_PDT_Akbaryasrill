-- UAS-PDT/postgres_custom/postgres-init/init.sql
-- Inisialisasi untuk database library_db (PostgreSQL + Citus)

-- Buat ekstensi Citus (sudah tersedia di image Citus resmi)

-- Buat ekstensi FDW untuk menghubungkan ke analytics_db
CREATE EXTENSION postgres_fdw;

-- Buat SERVER untuk koneksi ke analytics_db
-- HOST adalah nama service di docker-compose.yml
-- PORT adalah port PostgreSQL di kontainer analytics_db
CREATE SERVER analytics_server
    FOREIGN DATA WRAPPER postgres_fdw
    OPTIONS (host 'analytics_db', port '5432', dbname 'analyticsdb');

-- Buat USER MAPPING untuk server analytics_server
-- Sesuaikan user dan password dengan yang ada di docker-compose.yml untuk analytics_db
CREATE USER MAPPING FOR admin
    SERVER analytics_server
    OPTIONS (user 'admin', password 'password');

-- Tabel users (distribusi tidak diperlukan, ini adalah lookup table)
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'mahasiswa' -- 'admin' atau 'mahasiswa'
);

-- Tabel books (akan di-shard)
CREATE TABLE books (
    book_id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    author VARCHAR(255) NOT NULL,
    year INT,
    category VARCHAR(100)
);

-- Shard tabel books berdasarkan book_id
SELECT create_distributed_table('books', 'book_id');

-- Tabel borrow_logs (akan di-shard)
CREATE TABLE borrow_logs (
    log_id SERIAL PRIMARY KEY,
    book_id INT NOT NULL,
    user_id INT NOT NULL,
    borrowed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    return_at TIMESTAMP WITH TIME ZONE NOT NULL,
    returned_at TIMESTAMP WITH TIME ZONE
);

-- Shard tabel borrow_logs berdasarkan log_id
SELECT create_distributed_table('borrow_logs', 'log_id');

-- Buat FOREIGN TABLES untuk mengakses tabel analitik dari analytics_db
-- Ini memungkinkan library_db melihat data dari analytics_db seolah-olah lokal
CREATE FOREIGN TABLE books_summary (
    book_id INT,
    total_review INT,
    avg_rating NUMERIC(3,2),
    total_borrowed INT
) SERVER analytics_server OPTIONS (table_name 'books_summary');

CREATE FOREIGN TABLE borrows_per_user (
    user_id INT,
    user_name VARCHAR(255),
    total_borrows INT
) SERVER analytics_server OPTIONS (table_name 'borrows_per_user');

CREATE FOREIGN TABLE late_returns (
    log_id INT,
    book_id INT,
    user_id INT,
    borrowed_at TIMESTAMP WITH TIME ZONE,
    return_at TIMESTAMP WITH TIME ZONE,
    returned_at TIMESTAMP WITH TIME ZONE,
    late_days INT
) SERVER analytics_server OPTIONS (table_name 'late_returns');

-- Masukkan beberapa data awal (opsional)
INSERT INTO users (email, password, role) VALUES
('admin@kampus.com', 'admin_pass', 'admin'),
('Adam@kampus.com', 'adam_pass', 'mahasiswa'),
('Siti@kampus.com', 'siti_pass', 'mahasiswa'),
('Jany@kampus.com', 'jany_pass', 'mahasiswa');

INSERT INTO books (title, author, year, category) VALUES
('The Lord of the Rings', 'J.R.R. Tolkien', 1994, 'Fantasy'),
('The Hitchhiker''s Guide to the Galaxy', 'T. Egerton', 2002, 'Science Fiction'),
('Pride and Prejudice', 'Jane Austen', 1983, 'Romance'),
('Al Quran sebagai Cahaya Ilmu', 'Ust. Basmalah', 2024, 'Spiritual');