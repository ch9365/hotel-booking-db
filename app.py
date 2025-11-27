import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify, session, redirect

# 設定 Flask Secret Key (Session 需要用到，隨便打一串亂碼即可)
app = Flask(__name__)
app.secret_key = 'super_secret_key_hotel_project'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

@app.route('/')
def index():
    # 把登入資訊傳給前端
    user = session.get('user')
    return render_template('index.html', user=user)

# API: 簡易登入 (手機 + Email)
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    phone = data.get('phone')
    name = data.get('name') # 第一次登入順便填名字

    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. 先檢查這個 Email/Phone 是否存在
    cur.execute("SELECT * FROM guests WHERE email = %s OR phone = %s", (email, phone))
    user = cur.fetchone()

    if not user:
        # 2. 如果是新用戶，自動註冊
        if not name:
            return jsonify({"error": "新用戶請提供姓名"}), 400
        cur.execute(
            "INSERT INTO guests (first_name, last_name, email, phone, identification_number) VALUES (%s, '', %s, %s, 'N/A') RETURNING *",
            (name, email, phone)
        )
        user = cur.fetchone()
        conn.commit()

    cur.close()
    conn.close()

    # 3. 寫入 Session (代表已登入)
    session['user'] = user
    return jsonify({"message": "登入成功", "user": user})

# API: 登出
@app.route('/api/logout')
def logout():
    session.clear()
    return redirect('/')

# API: 搜尋空房 (維持不變，稍微加強註解)
@app.route('/api/search', methods=['GET'])
def search_rooms():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # SQL 邏輯：找出「狀態不是 Cancelled」且「時間重疊」的訂單，排除這些房間
    query = """
        SELECT r.room_id, r.room_number, t.type_name, t.base_price, t.description
        FROM rooms r
        JOIN room_types t ON r.type_id = t.type_id
        WHERE r.room_id NOT IN (
            SELECT room_id 
            FROM reservations
            WHERE status != 'Cancelled'  -- 關鍵：已取消的訂單不算佔用
            AND check_in_date < %s 
            AND check_out_date > %s
        )
        ORDER BY t.base_price, r.room_number;
    """
    # ... (原本的連線程式碼) ...
    # (這裡省略重複部分，請保留原本的 search 邏輯)
    # 為了完整性，下面補上精簡版：
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


# API: 建立訂房 (改為從 Session 抓 guest_id)
@app.route('/api/book', methods=['POST'])
def create_booking():
    if 'user' not in session:
        return jsonify({"error": "請先登入"}), 401

    data = request.json
    room_id = data.get('room_id')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    guest_id = session['user']['guest_id']

    conn = get_db_connection()
    cur = conn.cursor()
    
    # 計算價格
    cur.execute("SELECT base_price FROM rooms r JOIN room_types t ON r.type_id = t.type_id WHERE r.room_id = %s", (room_id,))
    price = cur.fetchone()['base_price']
    
    # 寫入訂單
    cur.execute(
        """INSERT INTO reservations (guest_id, room_id, check_in_date, check_out_date, total_price, status) 
           VALUES (%s, %s, %s, %s, %s, 'Confirmed') RETURNING reservation_id""",
        (guest_id, room_id, start_date, end_date, float(price))
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "訂房成功"})

# API: 取得我的訂單
@app.route('/api/my-bookings')
def my_bookings():
    if 'user' not in session:
        return jsonify([])

    guest_id = session['user']['guest_id']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT res.*, r.room_number, t.type_name 
        FROM reservations res
        JOIN rooms r ON res.room_id = r.room_id
        JOIN room_types t ON r.type_id = t.type_id
        WHERE res.guest_id = %s
        ORDER BY res.created_at DESC
    """, (guest_id,))
    bookings = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(bookings)

# API: 取消訂單
@app.route('/api/cancel', methods=['POST'])
def cancel_booking():
    if 'user' not in session:
        return jsonify({"error": "請先登入"}), 401

    data = request.json
    reservation_id = data.get('reservation_id')
    guest_id = session['user']['guest_id']

    conn = get_db_connection()
    cur = conn.cursor()
    
    # 執行取消 (狀態改為 Cancelled)
    # 必須檢查 guest_id 以防改到別人的訂單
    cur.execute("""
        UPDATE reservations 
        SET status = 'Cancelled' 
        WHERE reservation_id = %s AND guest_id = %s
    """, (reservation_id, guest_id))
    
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "訂單已取消"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
