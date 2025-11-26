import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# 從 Render 的環境變數抓取資料庫連線網址
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    if not DATABASE_URL:
        # 如果在本地端測試沒設定環境變數，會噴錯提醒你
        raise ValueError("DATABASE_URL environment variable is not set")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

@app.route('/')
def index():
    return render_template('index.html')

# API: 取得所有房型
@app.route('/api/room-types')
def get_room_types():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM room_types ORDER BY base_price ASC;")
        types = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(types)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: 搜尋空房
@app.route('/api/search', methods=['GET'])
def search_rooms():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        return jsonify({"error": "Please provide start_date and end_date"}), 400

    # 核心 SQL 邏輯：找出「沒有」在該時段被預訂的房間
    query = """
        SELECT r.room_id, r.room_number, t.type_name, t.base_price, t.description
        FROM rooms r
        JOIN room_types t ON r.type_id = t.type_id
        WHERE r.room_id NOT IN (
            SELECT room_id 
            FROM reservations
            WHERE status != 'Cancelled'
            AND check_in_date < %s 
            AND check_out_date > %s
        )
        ORDER BY t.base_price, r.room_number;
    """
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, (end_date, start_date))
        rooms = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rooms)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: 建立訂房
@app.route('/api/book', methods=['POST'])
def create_booking():
    data = request.json
    guest_name = data.get('guest_name')
    guest_email = data.get('guest_email')
    room_id = data.get('room_id')
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. 簡易建立顧客 (實務上應先檢查是否存在)
        cur.execute(
            "INSERT INTO guests (first_name, last_name, email, phone, identification_number) VALUES (%s, %s, %s, %s, %s) RETURNING guest_id",
            (guest_name, '', guest_email, '0000000000', 'N/A')
        )
        guest_id = cur.fetchone()['guest_id']

        # 2. 計算價格 (單價 * 天數)
        cur.execute("SELECT base_price FROM rooms r JOIN room_types t ON r.type_id = t.type_id WHERE r.room_id = %s", (room_id,))
        price_per_night = cur.fetchone()['base_price']
        
        from datetime import datetime
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        nights = (d2 - d1).days
        total_price = float(price_per_night) * max(1, nights)

        # 3. 寫入訂單
        cur.execute(
            """INSERT INTO reservations (guest_id, room_id, check_in_date, check_out_date, total_price, status) 
               VALUES (%s, %s, %s, %s, %s, 'Confirmed') RETURNING reservation_id""",
            (guest_id, room_id, start_date, end_date, total_price)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Booking successful!", "total_price": total_price})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Render 預設使用 PORT 環境變數，若無則用 10000
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
