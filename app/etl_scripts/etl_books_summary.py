# UAS-PDT/app/etl_scripts/etl_books_summary.py

import psycopg2
from pymongo import MongoClient
import os

# Konfigurasi Database dari environment variables
# Koneksi ke library_db
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')

# Koneksi ke analytics_db
ANALYTICS_HOST = os.getenv('ANALYTICS_HOST')
ANALYTICS_PORT = os.getenv('ANALYTICS_PORT')
ANALYTICS_DB = os.getenv('ANALYTICS_DB')
ANALYTICS_USER = os.getenv('ANALYTICS_USER')
ANALYTICS_PASSWORD = os.getenv('ANALYTICS_PASSWORD')

# Koneksi ke MongoDB
MONGO_HOST = os.getenv('MONGO_HOST')
MONGO_PORT = int(os.getenv('MONGO_PORT'))
MONGO_USERNAME = os.getenv('MONGO_USERNAME')
MONGO_PASSWORD = os.getenv('MONGO_PASSWORD')

def run_etl_books_summary():
    try:
        # Koneksi ke Library DB
        conn_lib = psycopg2.connect(
            host=POSTGRES_HOST, port=POSTGRES_PORT, database=POSTGRES_DB,
            user=POSTGRES_USER, password=POSTGRES_PASSWORD
        )
        cur_lib = conn_lib.cursor()

        # Koneksi ke Analytics DB
        conn_ana = psycopg2.connect(
            host=ANALYTICS_HOST, port=ANALYTICS_PORT, database=ANALYTICS_DB,
            user=ANALYTICS_USER, password=ANALYTICS_PASSWORD
        )
        cur_ana = conn_ana.cursor()

        # Koneksi ke MongoDB
        mongo_client = MongoClient(
            host=MONGO_HOST, port=MONGO_PORT,
            username=MONGO_USERNAME, password=MONGO_PASSWORD
        )
        reviews_collection = mongo_client.librarydb.reviews # Asumsi nama DB MongoDB 'librarydb'

        print("Running ETL for books_summary...")

        # 1. TRUNCATE tabel books_summary di analytics_db
        cur_ana.execute("TRUNCATE TABLE books_summary RESTART IDENTITY;")

        # 2. Extract data buku dari Library DB
        cur_lib.execute("SELECT book_id FROM books")
        book_ids = [row[0] for row in cur_lib.fetchall()]

        books_summary_data = []

        for book_id in book_ids:
            # Hitung total review dan rata-rata rating dari MongoDB
            mongo_doc = reviews_collection.find_one({"book_id": book_id})
            total_review = 0
            avg_rating = 0.0
            if mongo_doc and 'reviews' in mongo_doc and mongo_doc['reviews']:
                total_review = len(mongo_doc['reviews'])
                ratings = [r['rating'] for r in mongo_doc['reviews'] if 'rating' in r]
                if ratings:
                    avg_rating = sum(ratings) / len(ratings)

            # Hitung total peminjaman dari Library DB
            cur_lib.execute("SELECT COUNT(*) FROM borrow_logs WHERE book_id = %s", (book_id,))
            total_borrowed = cur_lib.fetchone()[0]

            books_summary_data.append((book_id, total_review, round(avg_rating, 2), total_borrowed))

        # 3. Load data ke Analytics DB
        for book_id, total_review, avg_rating, total_borrowed in books_summary_data:
            cur_ana.execute(
                """
                INSERT INTO books_summary (book_id, total_review, avg_rating, total_borrowed)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (book_id) DO UPDATE SET
                    total_review = EXCLUDED.total_review,
                    avg_rating = EXCLUDED.avg_rating,
                    total_borrowed = EXCLUDED.total_borrowed;
                """,
                (book_id, total_review, avg_rating, total_borrowed)
            )
        conn_ana.commit()
        print("ETL for books_summary completed successfully.")

    except Exception as e:
        print(f"Error during ETL for books_summary: {e}")
        if 'conn_ana' in locals() and conn_ana:
            conn_ana.rollback()
    finally:
        if 'conn_lib' in locals() and conn_lib:
            conn_lib.close()
        if 'conn_ana' in locals() and conn_ana:
            conn_ana.close()
        if 'mongo_client' in locals() and mongo_client:
            mongo_client.close()

if __name__ == '__main__':
    run_etl_books_summary()