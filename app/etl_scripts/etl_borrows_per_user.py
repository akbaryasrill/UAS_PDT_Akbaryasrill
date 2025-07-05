# UAS-PDT/app/etl_scripts/etl_borrows_per_user.py

import psycopg2
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

def run_etl_borrows_per_user():
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

        print("Running ETL for borrows_per_user...")

        # 1. TRUNCATE tabel borrows_per_user di analytics_db
        cur_ana.execute("TRUNCATE TABLE borrows_per_user RESTART IDENTITY;")

        # 2. Extract dan Transform: Hitung total peminjaman per user
        cur_lib.execute("""
            SELECT
                u.user_id,
                u.email AS user_name, -- Atau kolom nama jika ada
                COUNT(bl.log_id) AS total_borrows
            FROM users u
            JOIN borrow_logs bl ON u.user_id = bl.user_id
            GROUP BY u.user_id, u.email;
        """)
        borrows_data = cur_lib.fetchall()

        # 3. Load data ke Analytics DB
        for user_id, user_name, total_borrows in borrows_data:
            cur_ana.execute(
                """
                INSERT INTO borrows_per_user (user_id, user_name, total_borrows)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    user_name = EXCLUDED.user_name,
                    total_borrows = EXCLUDED.total_borrows;
                """,
                (user_id, user_name, total_borrows)
            )
        conn_ana.commit()
        print("ETL for borrows_per_user completed successfully.")

    except Exception as e:
        print(f"Error during ETL for borrows_per_user: {e}")
        if 'conn_ana' in locals() and conn_ana:
            conn_ana.rollback()
    finally:
        if 'conn_lib' in locals() and conn_lib:
            conn_lib.close()
        if 'conn_ana' in locals() and conn_ana:
            conn_ana.close()

if __name__ == '__main__':
    run_etl_borrows_per_user()