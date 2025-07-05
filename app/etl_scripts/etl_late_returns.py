# UAS-PDT/app/etl_scripts/etl_late_returns.py

import psycopg2
from datetime import datetime
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

def run_etl_late_returns():
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

        print("Running ETL for late_returns...")

        # 1. TRUNCATE tabel late_returns di analytics_db
        cur_ana.execute("TRUNCATE TABLE late_returns RESTART IDENTITY;")

        # 2. Extract dan Transform: Cari peminjaman yang terlambat
        cur_lib.execute("""
            SELECT
                log_id,
                book_id,
                user_id,
                borrowed_at,
                return_at,
                returned_at
            FROM borrow_logs
            WHERE returned_at IS NULL AND return_at < CURRENT_TIMESTAMP
            OR (returned_at IS NOT NULL AND returned_at > return_at);
        """)
        late_borrows = cur_lib.fetchall()

        late_returns_data = []
        for log_id, book_id, user_id, borrowed_at, return_at, returned_at in late_borrows:
            # Hitung keterlambatan hari
            if returned_at:
                late_days = (returned_at - return_at).days
            else: # Belum dikembalikan dan sudah melewati batas
                late_days = (datetime.now(return_at.tzinfo) - return_at).days # Pastikan timezone aware

            if late_days > 0:
                late_returns_data.append((log_id, book_id, user_id, borrowed_at, return_at, returned_at, late_days))

        # 3. Load data ke Analytics DB
        for log_id, book_id, user_id, borrowed_at, return_at, returned_at, late_days in late_returns_data:
            cur_ana.execute(
                """
                INSERT INTO late_returns (log_id, book_id, user_id, borrowed_at, return_at, returned_at, late_days)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (log_id) DO UPDATE SET
                    book_id = EXCLUDED.book_id,
                    user_id = EXCLUDED.user_id,
                    borrowed_at = EXCLUDED.borrowed_at,
                    return_at = EXCLUDED.return_at,
                    returned_at = EXCLUDED.returned_at,
                    late_days = EXCLUDED.late_days;
                """,
                (log_id, book_id, user_id, borrowed_at, return_at, returned_at, late_days)
            )
        conn_ana.commit()
        print("ETL for late_returns completed successfully.")

    except Exception as e:
        print(f"Error during ETL for late_returns: {e}")
        if 'conn_ana' in locals() and conn_ana:
            conn_ana.rollback()
    finally:
        if 'conn_lib' in locals() and conn_lib:
            conn_lib.close()
        if 'conn_ana' in locals() and conn_ana:
            conn_ana.close()

if __name__ == '__main__':
    run_etl_late_returns()