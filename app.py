import os
import psycopg2
from psycopg2.extras import RealDictCursor
# RealDictCursor 讓資料庫查詢結果變成 Dictionary(key-value)，而不是預設的 Tuple (index)，這樣就可以用 row['email'] 取值
from flask import Flask, render_template, request, jsonify, session, redirect
from datetime import datetime

app = Flask(__name__)
# 設定 Session 的加密金鑰，用於簽署 cookie，確保用戶登入狀態安全
app.secret_key = 'hotel_project_secret_key_12345'

# 從環境變數取得資料庫連線字串 (通常格式為 postgres://user:pass@host:port/dbname)
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    # cursor_factory=RealDictCursor 設定回傳格式為字典
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn


# 頁面路由
@app.route('/')
def index():
    user = session.get('user')
    return render_template('index.html', user=user)


# API 路由：使用者認證
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json # 取得前端傳來的 JSON 資料
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')

        # 簡單後端驗證，防止空值
        if not name or not email or not phone:
            return jsonify({"error": "請輸入完整的姓名、Email 與手機號碼"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        
        # 查詢資料庫：嚴格比對姓名、Email 和電話
        # 使用 %s 參數化查詢防止 SQL Injection 攻擊
        cur.execute("""
            SELECT * FROM guests 
            WHERE name = %s AND email = %s AND phone = %s
        """, (name, email, phone))
        
        user = cur.fetchone()# 取得單筆結果
        cur.close()
        conn.close()

        if user:
            # 處理日期格式，因 datetime 物件不能直接轉 JSON，需先轉成字串
            if user.get('birth_date'):
                user['birth_date'] = user['birth_date'].strftime('%Y-%m-%d')
            
            # 將使用者資訊存入 Session (代表登入成功)
            session['user'] = user
            return jsonify({"message": "登入成功", "user": user})
        else:
            return jsonify({"error": "資料不正確，請檢查輸入或前往註冊"}), 401
            
    except Exception as e: # 在伺服器 log 印出錯誤以便除錯
        print("Login Error:", e)
        return jsonify({"error": "系統錯誤"}), 500

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        birth_date = data.get('birth_date') or None
        # 如果空字串轉為 None (資料庫 NULL)
        gender = data.get('gender') or None

        if not name or not email or not phone:
            return jsonify({"error": "姓名、Email 與手機為必填欄位"}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        # 1. 檢查是否重複：Email 或電話已被使用就不能註冊
        cur.execute("SELECT * FROM guests WHERE email = %s OR phone = %s", (email, phone))
        existing = cur.fetchone()

        if existing:
            cur.close(); conn.close()
            return jsonify({"error": "此 Email 或手機已註冊過，請直接登入"}), 409

        # 2. 新增用戶
        # RETURNING * 可以直接回傳剛插入的那筆資料，省去再 SELECT 一次
        cur.execute("""
            INSERT INTO guests (name, email, phone, birth_date, gender)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING * 
        """, (name, email, phone, birth_date, gender))
        
        new_user = cur.fetchone()
        conn.commit()# 寫入操作必須 commit 才會生效
        cur.close(); conn.close()

        # 格式化日期以便回傳前端
        if new_user.get('birth_date'):
            new_user['birth_date'] = new_user['birth_date'].strftime('%Y-%m-%d')
            
        # 註冊後直接幫使用者登入
        session['user'] = new_user
        return jsonify({"message": "註冊成功", "user": new_user})

    except Exception as e:
        print("Register Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/logout')
def logout():
    session.clear() # 清除 Session 中的所有資料
    return redirect('/') # 導回首頁

# API 路由：個人資料管理
@app.route('/api/profile', methods=['GET'])
def get_profile():
    # 權限檢查：未登入者不能存取
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    conn = get_db_connection(); cur = conn.cursor()
    # 重新從資料庫抓取最新資料 (避免 Session 內的資料過舊)
    cur.execute("SELECT * FROM guests WHERE guest_id = %s", (session['user']['guest_id'],))
    user = cur.fetchone()
    cur.close(); conn.close()
    
    if user and user.get('birth_date'):
        user['birth_date'] = user['birth_date'].strftime('%Y-%m-%d')
        
    # 更新 session 保持同步
    session['user'] = user
    return jsonify(user)

@app.route('/api/profile', methods=['POST'])
def update_profile():
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    data = request.json
    
    # 取得要更新的欄位
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

# API 路由：訂房邏輯
@app.route('/api/search', methods=['GET'])
def search_rooms():
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    cap = request.args.get('capacity')
    
    if not start or not end: return jsonify({"error": "請選日期"}), 400
    
    # 後端防呆：日期檢查
    today = datetime.now().strftime('%Y-%m-%d')
    if start < today: return jsonify({"error": "入住日期不能是過去"}), 400
    if start >= end: return jsonify({"error": "退房日期必須晚於入住日期"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    # 1. 找出這段時間已被預訂的房間 ID
    query_booked = """
        SELECT room_id FROM reservations 
        WHERE status != 'Cancelled'
        AND check_in_date < %s AND check_out_date > %s
    """
    cur.execute(query_booked, (end, start))
    booked_room_ids = [r['room_id'] for r in cur.fetchall()]
    
    # 2. 查詢所有房間與房型資訊
    query_rooms = """
        SELECT r.room_id, r.room_number, t.type_name, t.base_price, t.description, t.capacity
        FROM rooms r 
        JOIN room_types t ON r.type_id = t.type_id
        ORDER BY t.base_price, r.room_number
    """
    cur.execute(query_rooms)
    all_rooms = cur.fetchall()
    cur.close(); conn.close()

    # 3. 過濾並分組：把可用房間依「房型」歸類
    grouped_rooms = {}
    
    for r in all_rooms:
        # 過濾掉人數不足的 (如果有選人數)
        if cap and int(cap) > 0 and r['capacity'] < int(cap):
            continue
            
        # 過濾掉已被預訂的房間
        if r['room_id'] in booked_room_ids:
            continue
            
        # 依照房型名稱分組
        t_name = r['type_name']
        if t_name not in grouped_rooms:
            grouped_rooms[t_name] = {
                'type_name': t_name,
                'description': r['description'],
                'base_price': r['base_price'],
                'capacity': r['capacity'],
                'available_rooms': [] # 這裡存該房型下所有可用的房間
            }
        
        # 將可用房間加入該房型的清單中
        grouped_rooms[t_name]['available_rooms'].append({
            'room_id': r['room_id'],
            'room_number': r['room_number']
        })

    # 轉換成 List 回傳
    result = list(grouped_rooms.values())
    return jsonify(result)


@app.route('/api/book', methods=['POST'])
def create_booking():
    if 'user' not in session: return jsonify({"error": "未登入"}), 401
    data = request.json
    
    # 安全性檢查：不能只信前端傳來的價格，必須重新從資料庫撈取房價
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT base_price FROM rooms r JOIN room_types t ON r.type_id=t.type_id WHERE room_id=%s", (data['room_id'],))
    res = cur.fetchone()
    if not res: return jsonify({"error": "房間不存在"}), 404
    
    price = float(res['base_price'])
    
    # 計算總價：房價 * 天數
    d1 = datetime.strptime(data['start_date'], "%Y-%m-%d")
    d2 = datetime.strptime(data['end_date'], "%Y-%m-%d")
    days = (d2 - d1).days
    if days < 1: days = 1 # 至少算一天
    
    total = price * days
    
    # 寫入訂單
    cur.execute("INSERT INTO reservations (guest_id, room_id, check_in_date, check_out_date, total_price, status) VALUES (%s, %s, %s, %s, %s, 'Confirmed')",
                (session['user']['guest_id'], data['room_id'], data['start_date'], data['end_date'], total))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"message": "成功", "total_price": total})

# 查詢使用者的歷史訂單
@app.route('/api/my-bookings')
def my_bookings():
    if 'user' not in session: return jsonify([])
    conn = get_db_connection(); cur = conn.cursor()
    # 使用 JOIN 取得 訂單+房間+房型 的完整資訊
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
    
    # 取消訂單：不是刪除資料，而是將狀態改為 Cancelled
    # WHERE 子句多加了 guest_id=%s，防止使用者惡意取消別人的訂單
    cur.execute("UPDATE reservations SET status='Cancelled' WHERE reservation_id=%s AND guest_id=%s",
                (request.json['reservation_id'], session['user']['guest_id']))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"message": "已取消"})

if __name__ == '__main__':
    # 根據 Render 或 Heroku 的環境變數設定 Port，本地開發預設 10000
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
