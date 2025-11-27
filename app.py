import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify, session, redirect
from datetime import datetime

app = Flask(__name__)
# 設定 Session 密鑰
app.secret_key = 'hotel_project_secret_key_12345'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

@app.route('/')
def index():
    user = session.get('user')
    return render_template('index.html', user=user)

# API: 登入 (嚴格版：Email 和 Phone 必須同時匹配)
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')

    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. 檢查是否已存在 (Email 或 Phone)
    cur.execute("SELECT * FROM guests WHERE email = %s OR phone = %s", (email, phone))
    existing_users = cur.fetchall()
    
    user = None
    
    if existing_users:
        # 若有找到資料，檢查是否完全匹配 (Email 和 Phone 都一樣)
        for u in existing_users:
            if u['email'] == email and u['phone'] == phone:
                user = u
                break
        
        if user:
            # 登入成功 (完全匹配)
            pass
        else:
            # 只對了一個 (例如 Email 對了但 Phone 不對)，視為衝突
            cur.close()
            conn.close()
            return jsonify({"error": "此 Email 或手機已被其他帳號使用，請確認資料是否正確"}), 409
            
    else:
        # 2. 完全沒找到 -> 註冊新用戶
        if not name:
            return jsonify({"error": "新用戶請填寫姓名"}), 400
        cur.execute(
            "INSERT INTO guests (first_name, last_name, email, phone, identification_number) VALUES (%s, '', %s, %s, 'N/A') RETURNING *",
            (name, email, phone)
        )
        user = cur.fetchone()
        conn.commit()

    cur.close()
    conn.close()

    # 登入成功寫入 Session
    session['user'] = user
    return jsonify({"message": "登入成功", "user": user})

# API: 登出
@app.route('/api/logout')
def logout():
    session.clear()
    return redirect('/')

# API: 取得個人資料 (最新)
@app.route('/api/profile', methods=['GET'])
def get_profile():
    if 'user' not in session:
        return jsonify({"error": "未登入"}), 401
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM guests WHERE guest_id = %s", (session['user']['guest_id'],))
    user = cur.fetchone()
    cur.close()
    conn.close()
    
    # 格式化日期 (如果有生日)
    if user.get('birth_date'):
        user['birth_date'] = user['birth_date'].strftime('%Y-%m-%d')
        
    session['user'] = user # 更新 session
    return jsonify(user)

# API: 更新個人資料
@app.route('/api/profile', methods=['POST'])
def update_profile():
    if 'user' not in session:
        return jsonify({"error": "未登入"}), 401

    data = request.json
    first_name = data.get('first_name')
    email = data.get('email')
    phone = data.get('phone')
    birth_date = data.get('birth_date') # 格式 YYYY-MM-DD
    gender = data.get('gender')
    
    # 空字串轉為 None，避免 SQL 錯誤
    if not birth_date: birth_date = None

    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE guests 
            SET first_name = %s, email = %s, phone = %s, birth_date = %s, gender = %s
            WHERE guest_id = %s
        """, (first_name, email, phone, birth_date, gender, session['user']['guest_id']))
        conn.commit()
    except Exception as e:
        return jsonify({"error": "更新失敗，可能 Email 或手機重複"}), 400
    
    cur.close()
    conn.close()
    return jsonify({"message": "資料更新成功"})

# API: 搜尋空房
@app.route('/api/search', methods=['GET'])
def search_rooms():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    capacity = request.args.get('capacity')
    
    if not start_date or not end_date:
        return jsonify({"error": "請選擇日期"}), 400

    query = """
        SELECT r.room_id, r.room_number, t.type_name, t.base_price, t.description, t.capacity
        FROM rooms r
        JOIN room_types t ON r.type_id = t.type_id
        WHERE r.room_id NOT IN (
            SELECT room_id 
            FROM reservations
            WHERE status != 'Cancelled'
            AND check_in_date < %s 
            AND check_out_date > %s
        )
    """
    params = [end_date, start_date]

    if capacity and int(capacity) > 0:
        query += " AND t.capacity >= %s"
        params.append(capacity)

    query += " ORDER BY t.base_price, r.room_number;"
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, tuple(params))
        rooms = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rooms)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: 建立訂單 (含天數計算)
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
    
    # 1. 查單價
    cur.execute("SELECT base_price FROM rooms r JOIN room_types t ON r.type_id = t.type_id WHERE r.room_id = %s", (room_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "房間不存在"}), 404
    base_price = float(row['base_price'])
    
    # 2. 計算天數與總價
    d1 = datetime.strptime(start_date, "%Y-%m-%d")
    d2 = datetime.strptime(end_date, "%Y-%m-%d")
    nights = (d2 - d1).days
    if nights < 1: nights = 1
    
    total_price = base_price * nights

    # 3. 寫入
    cur.execute(
        """INSERT INTO reservations (guest_id, room_id, check_in_date, check_out_date, total_price, status) 
           VALUES (%s, %s, %s, %s, %s, 'Confirmed') RETURNING reservation_id""",
        (guest_id, room_id, start_date, end_date, total_price)
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": "訂房成功", "total_price": total_price})

# API: 我的訂單
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
