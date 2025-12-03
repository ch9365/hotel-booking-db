import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify, session, redirect
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'hotel_project_secret_key_12345'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

@app.route('/')
def index():
    user = session.get('user')
    return render_template('index.html', user=user)

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')

        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. 檢查 Email 或 Phone 是否存在
        cur.execute("SELECT * FROM guests WHERE email = %s OR phone = %s", (email, phone))
        existing_users = cur.fetchall()
        
        user = None
        
        if existing_users:
            for u in existing_users:
                # 情況 A: 完全匹配
                if u['email'] == email and u['phone'] == phone:
                    user = u
                    break
                
                # 情況 B: Email 對，手機不對 -> 更新手機
                if u['email'] == email and u['phone'] != phone:
                    cur.execute("UPDATE guests SET phone = %s WHERE guest_id = %s", (phone, u['guest_id']))
                    conn.commit()
                    u['phone'] = phone
                    user = u
                    break

                # 情況 C: 手機對，Email 不對 -> 更新 Email
                if u['phone'] == phone and u['email'] != email:
                    cur.execute("UPDATE guests SET email = %s WHERE guest_id = %s", (email, u['guest_id']))
                    conn.commit()
                    u['email'] = email
                    user = u
                    break
            
            if not user:
                cur.close(); conn.close()
                return jsonify({"error": "此 Email 或手機已被其他帳號使用"}), 409
                
        else:
            # 2. 註冊新用戶
            if not name:
                cur.close(); conn.close()
                return jsonify({"error": "新用戶請填寫姓名"}), 400
                
            # 這裡務必確認資料庫欄位是 name 不是 first_name
            cur.execute(
                "INSERT INTO guests (name, email, phone, identification_number) VALUES (%s, %s, %s, 'N/A') RETURNING *",
                (name, email, phone)
            )
            user = cur.fetchone()
            conn.commit()

        cur.close()
        conn.close()

        session['user'] = user
        return jsonify({"message": "登入成功", "user": user})
        
    except Exception as e:
        print("Login Error:", e) # 這行會印在 Render Log 裡方便除錯
        return jsonify({"error": str(e)}), 500


@app.route('/api/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/api/profile', methods=['GET'])
def get_profile():
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT * FROM guests WHERE guest_id = %s", (session['user']['guest_id'],))
    user = cur.fetchone()
    cur.close(); conn.close()
    
    if user.get('birth_date'): user['birth_date'] = user['birth_date'].strftime('%Y-%m-%d')
    session['user'] = user
    return jsonify(user)

@app.route('/api/profile', methods=['POST'])
def update_profile():
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    data = request.json
    
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    birth_date = data.get('birth_date') or None
    gender = data.get('gender')

    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE guests 
            SET name = %s, email = %s, phone = %s, birth_date = %s, gender = %s
            WHERE guest_id = %s
        """, (name, email, phone, birth_date, gender, session['user']['guest_id']))
        conn.commit()
    except Exception:
        return jsonify({"error": "更新失敗"}), 400
    
    cur.close(); conn.close()
    return jsonify({"message": "更新成功"})

@app.route('/api/search', methods=['GET'])
def search_rooms():
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    cap = request.args.get('capacity')
    
    if not start or not end: return jsonify({"error": "請選日期"}), 400
    # 【後端防呆】檢查日期順序
    if start >= end: return jsonify({"error": "退房日期必須晚於入住日期"}), 400

    query = """
        SELECT r.room_id, r.room_number, t.type_name, t.base_price, t.description, t.capacity
        FROM rooms r JOIN room_types t ON r.type_id = t.type_id
        WHERE r.room_id NOT IN (
            SELECT room_id FROM reservations WHERE status != 'Cancelled'
            AND check_in_date < %s AND check_out_date > %s
        )
    """
    params = [end, start]
    if cap and int(cap)>0: query+=" AND t.capacity >= %s"; params.append(cap)
    query+=" ORDER BY t.base_price"
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(query, tuple(params))
    rooms = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rooms)

@app.route('/api/book', methods=['POST'])
def create_booking():
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    data = request.json
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT base_price FROM rooms r JOIN room_types t ON r.type_id=t.type_id WHERE room_id=%s", (data['room_id'],))
    price = float(cur.fetchone()['base_price'])
    
    # 計算天數
    d1 = datetime.strptime(data['start_date'], "%Y-%m-%d")
    d2 = datetime.strptime(data['end_date'], "%Y-%m-%d")
    days = (d2 - d1).days
    if days < 1: days = 1
    
    total = price * days
    
    cur.execute("INSERT INTO reservations (guest_id, room_id, check_in_date, check_out_date, total_price, status) VALUES (%s, %s, %s, %s, %s, 'Confirmed')",
                (session['user']['guest_id'], data['room_id'], data['start_date'], data['end_date'], total))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"message": "成功", "total_price": total})

@app.route('/api/my-bookings')
def my_bookings():
    if 'user' not in session: return jsonify([])
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT res.*, r.room_number, t.type_name 
        FROM reservations res JOIN rooms r ON res.room_id=r.room_id JOIN room_types t ON r.type_id=t.type_id
        WHERE res.guest_id=%s ORDER BY res.created_at DESC
    """, (session['user']['guest_id'],))
    res = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(res)

@app.route('/api/cancel', methods=['POST'])
def cancel_booking():
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE reservations SET status='Cancelled' WHERE reservation_id=%s AND guest_id=%s",
                (request.json['reservation_id'], session['user']['guest_id']))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"message": "已取消"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
