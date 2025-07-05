# UAS-PDT/app/app.py

from flask import Flask, request, jsonify
import psycopg2
from pymongo import MongoClient
import redis
from datetime import datetime, timedelta
import os
import json # Untuk menyimpan review sebagai array JSON di MongoDB
import uuid # Untuk generate session token

app = Flask(__name__)

# Konfigurasi Database dari environment variables
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')

MONGO_HOST = os.getenv('MONGO_HOST')
MONGO_PORT = int(os.getenv('MONGO_PORT'))
MONGO_USERNAME = os.getenv('MONGO_USERNAME')
MONGO_PASSWORD = os.getenv('MONGO_PASSWORD')

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT'))

ANALYTICS_HOST = os.getenv('ANALYTICS_HOST')
ANALYTICS_PORT = os.getenv('ANALYTICS_PORT')
ANALYTICS_DB = os.getenv('ANALYTICS_DB')
ANALYTICS_USER = os.getenv('ANALYTICS_USER')
ANALYTICS_PASSWORD = os.getenv('ANALYTICS_PASSWORD')

# Koneksi ke PostgreSQL (Library DB)
def get_pg_conn():
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    return conn

# Koneksi ke MongoDB
def get_mongo_client():
    client = MongoClient(
        host=MONGO_HOST,
        port=MONGO_PORT,
        username=MONGO_USERNAME,
        password=MONGO_PASSWORD
    )
    return client

# Koneksi ke Redis
def get_redis_client():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    return r

# --- Middleware Autentikasi (Contoh Sederhana) ---
def authenticate_user(token):
    r = get_redis_client()
    user_id = r.get(f"session:{token}")
    if user_id:
        return int(user_id)
    return None

def authorize_role(user_id, required_role):
    conn = get_pg_conn()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE user_id = %s", (user_id,))
    user_role = cur.fetchone()
    conn.close()
    if user_role and user_role[0] == required_role:
        return True
    return False

# Dekorator untuk endpoint yang membutuhkan otentikasi
def login_required(f):
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"message": "Authorization token missing"}), 401
        token = token.replace('Bearer ', '')
        user_id = authenticate_user(token)
        if not user_id:
            return jsonify({"message": "Invalid or expired token"}), 401
        request.user_id = user_id # Tambahkan user_id ke objek request
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__ # Penting untuk Flask
    return wrapper

# Dekorator untuk endpoint yang membutuhkan role admin
def admin_required(f):
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"message": "Authorization token missing"}), 401
        token = token.replace('Bearer ', '')
        user_id = authenticate_user(token)
        if not user_id:
            return jsonify({"message": "Invalid or expired token"}), 401
        if not authorize_role(user_id, 'admin'):
            return jsonify({"message": "Forbidden: Admin access required"}), 403
        request.user_id = user_id # Tambahkan user_id ke objek request
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# --- Endpoint API (Sesuai Laporan) ---

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    conn = get_pg_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, password FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    conn.close()

    if user and user[1] == password: # Implementasi hashing password di dunia nyata!
        token = str(uuid.uuid4())
        r = get_redis_client()
        r.set(f"session:{token}", user[0], ex=3600) # Token berlaku 1 jam
        return jsonify({"message": "Login successful", "token": token}), 200
    return jsonify({"message": "Invalid credentials"}), 401

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    token = request.headers.get('Authorization').replace('Bearer ', '')
    r = get_redis_client()
    r.delete(f"session:{token}")
    return jsonify({"message": "Logout successful"}), 200

@app.route('/register', methods=['POST'])
@admin_required # Hanya admin yang bisa registrasi user baru
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'mahasiswa') # Default role

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    conn = get_pg_conn()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (email, password, role) VALUES (%s, %s, %s) RETURNING user_id", (email, password, role))
        user_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"message": "User registered successfully", "user_id": user_id}), 201
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({"message": "User with this email already exists"}), 409
    finally:
        conn.close()

# Contoh Endpoint /books (GET) - Menggabungkan data dari 3 DB
@app.route('/books', methods=['GET'])
@login_required
def get_all_books():
    books_data = []
    conn_pg = get_pg_conn()
    cur_pg = conn_pg.cursor()
    # Tambahkan kolom 'quantity' di SELECT
    cur_pg.execute("SELECT book_id, title, author, year, category, quantity FROM books")
    pg_books = cur_pg.fetchall()
    conn_pg.close()

    mongo_client = get_mongo_client()
    reviews_collection = mongo_client.librarydb.reviews 

    r = get_redis_client()

    for book_id, title, author, year, category, quantity in pg_books: # Tambahkan 'quantity' di sini
        book_info = {
            "book_id": book_id,
            "title": title,
            "author": author,
            "year": year,
            "category": category,
            "quantity": quantity # Tambahkan quantity ke respons
        }

        # --- Modifikasi untuk Status Ketersediaan (berdasarkan quantity atau Redis) ---
        # Opsi 1: Status dari Redis (menyimpan jumlah tersedia)
        # Jika Anda ingin Redis menyimpan jumlah tersedia untuk akses cepat
        redis_available_count = r.get(f"book_available_count:{book_id}")
        if redis_available_count is not None:
             book_info["available_copies"] = int(redis_available_count)
             book_info["status"] = "available" if int(redis_available_count) > 0 else "out of stock"
        else:
             # Fallback ke quantity dari PG jika tidak ada di Redis
             book_info["available_copies"] = quantity
             book_info["status"] = "available" if quantity > 0 else "out of stock"
        # --- Akhir Modifikasi Status ---

        # Ambil review dari MongoDB (sama seperti sebelumnya)
        mongo_doc = reviews_collection.find_one({"book_id": book_id}, {"_id": 0, "reviews": 1})
        book_info["reviews"] = mongo_doc.get("reviews", []) if mongo_doc else []

        books_data.append(book_info)

    return jsonify(books_data), 200
# /books/<book_id>, /books (POST, PUT, DELETE), /review (POST, GET, PUT, DELETE)

# --- Modifikasi Endpoint Peminjaman Buku ---
@app.route('/borrow', methods=['POST'])
@login_required
def borrow_book():
    data = request.get_json()
    book_id = data.get('book_id')
    return_at_str = data.get('return_at') 

    if not book_id or not return_at_str:
        return jsonify({"message": "Book ID and return date/time are required"}), 400

    current_user_id = request.user_id

    conn_pg = get_pg_conn()
    cur_pg = conn_pg.cursor()
    r = get_redis_client()

    try:
        try:
            return_at = datetime.fromisoformat(return_at_str)
        except ValueError:
            return jsonify({"message": "Invalid return_at format. Use YYYY-MM-DD HH:MM:SS"}), 400

        # 1. Cek kuantitas buku di PostgreSQL
        cur_pg.execute("SELECT quantity FROM books WHERE book_id = %s FOR UPDATE", (book_id,)) # FOR UPDATE untuk mencegah race condition
        book = cur_pg.fetchone()

        if book is None:
            return jsonify({"message": "Book not found"}), 404
        
        current_quantity = book[0]

        if current_quantity <= 0:
            return jsonify({"message": "Book is currently out of stock"}), 400

        # 2. Kurangi kuantitas di PostgreSQL
        new_quantity = current_quantity - 1
        cur_pg.execute(
            "UPDATE books SET quantity = %s WHERE book_id = %s",
            (new_quantity, book_id)
        )

        # 3. Masukkan log peminjaman ke PostgreSQL
        cur_pg.execute(
            "INSERT INTO borrow_logs (book_id, user_id, borrowed_at, return_at) VALUES (%s, %s, CURRENT_TIMESTAMP, %s) RETURNING log_id",
            (book_id, current_user_id, return_at)
        )
        log_id = cur_pg.fetchone()[0]
        
        conn_pg.commit() # Commit transaksi PG setelah semua update

        # 4. Update jumlah tersedia di Redis (opsional, untuk cache ketersediaan cepat)
        r.set(f"book_available_count:{book_id}", new_quantity)

        return jsonify({"message": "Book borrowed successfully", "log_id": log_id, "remaining_quantity": new_quantity}), 201

    except Exception as e:
        conn_pg.rollback()
        return jsonify({"message": f"Error borrowing book: {str(e)}"}), 500
    finally:
        conn_pg.close()

# --- Endpoint Review (MongoDB) ---
@app.route('/review', methods=['POST'])
@login_required
def add_review():
    data = request.get_json()
    book_id = data.get('book_id')
    rating = data.get('rating')
    comment = data.get('comment')

    if not book_id or not rating:
        return jsonify({"message": "Book ID and rating are required"}), 400

    if not isinstance(rating, (int, float)) or not (1 <= rating <= 5):
        return jsonify({"message": "Rating must be a number between 1 and 5"}), 400

    user_id = request.user_id # Diambil dari dekorator @login_required

    mongo_client = get_mongo_client()
    reviews_collection = mongo_client.librarydb.reviews # Asumsi DB bernama 'librarydb'

    try:
        # Cek apakah ada dokumen untuk book_id ini
        existing_doc = reviews_collection.find_one({"book_id": book_id})

        new_review = {
            "user_id": user_id,
            "rating": rating,
            "comment": comment,
            "timestamp": datetime.now()
        }

        if existing_doc:
            # Jika dokumen sudah ada, tambahkan review ke array 'reviews'
            reviews_collection.update_one(
                {"book_id": book_id},
                {"$push": {"reviews": new_review}}
            )
            message = "Review added to existing book entry"
        else:
            # Jika dokumen belum ada, buat dokumen baru
            reviews_collection.insert_one({
                "book_id": book_id,
                "reviews": [new_review]
            })
            message = "New book entry created with review"

        return jsonify({"message": message, "review": new_review}), 201

    except Exception as e:
        return jsonify({"message": f"Error adding review: {str(e)}"}), 500
    finally:
        mongo_client.close()

# Anda juga mungkin ingin menambahkan endpoint GET untuk /review/<book_id>
# dan PUT/DELETE untuk review di masa mendatang.

# --- Modifikasi Endpoint Pengembalian Buku ---
@app.route('/return', methods=['POST'])
@login_required
def return_book():
    data = request.get_json()
    log_id = data.get('log_id')
    book_id = data.get('book_id') # book_id diperlukan untuk update quantity dan Redis
    
    if not log_id or not book_id:
        return jsonify({"message": "Log ID and Book ID are required"}), 400

    current_user_id = request.user_id

    conn_pg = get_pg_conn()
    cur_pg = conn_pg.cursor()
    r = get_redis_client()

    try:
        # 1. Cek log peminjaman di PostgreSQL
        cur_pg.execute(
            "SELECT user_id, book_id, return_at, returned_at FROM borrow_logs WHERE log_id = %s",
            (log_id,)
        )
        borrow_log = cur_pg.fetchone()

        if not borrow_log:
            return jsonify({"message": "Borrow log not found"}), 404
        
        if borrow_log[0] != current_user_id:
            return jsonify({"message": "Forbidden: You can only return your own borrowed books"}), 403

        if borrow_log[3] is not None:
            return jsonify({"message": "Book has already been returned"}), 400

        # 2. Update returned_at di PostgreSQL
        cur_pg.execute(
            "UPDATE borrow_logs SET returned_at = CURRENT_TIMESTAMP WHERE log_id = %s",
            (log_id,)
        )
        
        # 3. Tambah kuantitas di PostgreSQL
        cur_pg.execute(
            "UPDATE books SET quantity = quantity + 1 WHERE book_id = %s RETURNING quantity",
            (book_id,)
        )
        new_quantity = cur_pg.fetchone()[0] # Dapatkan kuantitas terbaru
        
        conn_pg.commit() # Commit transaksi PG

        # 4. Update jumlah tersedia di Redis (opsional, untuk cache ketersediaan cepat)
        r.set(f"book_available_count:{book_id}", new_quantity)

        return jsonify({"message": "Book returned successfully", "remaining_quantity": new_quantity}), 200

    except Exception as e:
        conn_pg.rollback()
        return jsonify({"message": f"Error returning book: {str(e)}"}), 500
    finally:
        conn_pg.close()

# --- Endpoint Analitik (FDW ke analytics_db) ---
@app.route('/analytics/late-returns', methods=['GET'])
@admin_required
def get_late_returns():
    conn = get_pg_conn() # Koneksi ke library_db yang memiliki FDW ke analytics_db
    cur = conn.cursor()
    # Query ke foreign table late_returns
    cur.execute("SELECT log_id, book_id, user_id, borrowed_at, return_at, returned_at, late_days FROM late_returns ORDER BY late_days DESC")
    late_data = [
        {
            "log_id": row[0],
            "book_id": row[1],
            "user_id": row[2],
            "borrowed_at": row[3].isoformat() if row[3] else None,
            "return_at": row[4].isoformat() if row[4] else None,
            "returned_at": row[5].isoformat() if row[5] else None,
            "late_days": row[6]
        } for row in cur.fetchall()
    ]
    conn.close()
    return jsonify(late_data), 200

# Endpoint analitik lainnya akan mengikuti pola serupa
# /analytics/books-summary, /analytics/borrows-per-user

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)