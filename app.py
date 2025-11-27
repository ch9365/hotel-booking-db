# 1. 確保表格都已建立 (如果已存在則不會重複建)
CREATE TABLE IF NOT EXISTS room_types (
    type_id SERIAL PRIMARY KEY,
    type_name VARCHAR(50) NOT NULL,
    description TEXT,
    base_price DECIMAL(10, 2) NOT NULL,
    capacity INT NOT NULL
);

CREATE TABLE IF NOT EXISTS rooms (
    room_id SERIAL PRIMARY KEY,
    room_number VARCHAR(10) NOT NULL UNIQUE,
    type_id INT NOT NULL REFERENCES room_types(type_id),
    current_status VARCHAR(20) DEFAULT 'Available'
);

CREATE TABLE IF NOT EXISTS guests (
    guest_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(20),
    identification_number VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS reservations (
    reservation_id SERIAL PRIMARY KEY,
    guest_id INT NOT NULL REFERENCES guests(guest_id),
    room_id INT NOT NULL REFERENCES rooms(room_id),
    check_in_date DATE NOT NULL,
    check_out_date DATE NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'Confirmed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

#2. 清空舊資料 (避免重複塞入)
TRUNCATE TABLE reservations, rooms, room_types, guests RESTART IDENTITY CASCADE;

# 3. 塞入房型資料
INSERT INTO room_types (type_name, base_price, capacity, description) VALUES
('標準單人房', 1500.00, 1, '適合背包客的經濟選擇'),
('豪華雙人房', 2800.00, 2, '情侶首選，附有獨立陽台'),
('溫馨四人房', 4500.00, 4, '家庭旅遊最愛，兩張大雙人床');

# 4. 塞入房間資料
# type_id 對應上面的順序：1=單人, 2=雙人, 3=四人
INSERT INTO rooms (room_number, type_id, current_status) VALUES
('101', 1, 'Available'),
('102', 1, 'Available'),
('201', 2, 'Available'),
('202', 2, 'Available'),
('203', 2, 'Available'),
('301', 3, 'Available');

# 5. 顯示結果確認一下
SELECT * FROM rooms;
