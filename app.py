import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify, session, redirect

app = Flask(__name__)
# 設定 Session 密鑰 (正式環境建議用更複雜的隨機字串)
app.secret_key = 'hotel_project_secret_key_12345'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

@app.route('/')
def index():
    # 將當前登入的 user 資訊傳給前端
    user = session.get('user')
    return render_template('index.html', user=user)

# API: 簡易登入 (無密碼)
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')

    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. 檢查用戶是否存在
    cur.execute("SELECT * FROM guests WHERE email = %s OR phone = %s", (email, phone))
    user = cur.fetchone()

    # 2. 若不存在則註冊
    if not user:
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

    # 3. 寫入 Session
    session['user'] = user
    return jsonify({"message": "登入成功", "user": user})

# API: 登出
@app.route('/api/logout')
def logout():
    session.clear()
    return redirect('/')

# API: 搜尋空房 (含人數篩選)
@app.route('/api/search', methods=['GET'])
def search_rooms():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    capacity = request.args.get('capacity') # 接收人數參數
    
    if not start_date or not end_date:
        return jsonify({"error": "請選擇日期"}), 400

    # SQL: 找出「未被預訂」或「訂單已取消」的房間
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

    # 若有人數篩選 (且值大於0)，加入 AND 條件
    if capacity and int(capacity) > 0:
        query += " AND t.capacity = %s"
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

# API: 建立訂單
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
    
    # 查價格
    cur.execute("SELECT base_price FROM rooms r JOIN room_types t ON r.type_id = t.type_id WHERE r.room_id = %s", (room_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "房間不存在"}), 404
        
    price = row['base_price']
    
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

# API: 我的訂單列表
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
    
    # 執行取消 (只能取消自己的訂單)
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
