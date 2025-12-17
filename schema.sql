-- 如果表格已存在則不重複建立 (方便重複執行)

--  房型表
CREATE TABLE IF NOT EXISTS room_types (
    type_id SERIAL PRIMARY KEY,
    type_name VARCHAR(50) NOT NULL,
    description TEXT,
    base_price DECIMAL(10, 2) NOT NULL,
    capacity INT NOT NULL
);

--  房間表
CREATE TABLE IF NOT EXISTS rooms (
    room_id SERIAL PRIMARY KEY,
    room_number VARCHAR(10) NOT NULL UNIQUE,
    type_id INT NOT NULL REFERENCES room_types(type_id),
    current_status VARCHAR(20) DEFAULT 'Available'
);

--  顧客表
CREATE TABLE IF NOT EXISTS guests (
    guest_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(20),
    identification_number VARCHAR(20)
);


-- 訂房表 (核心交易表)
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

-- 測試資料：初始化幾種房型與房間
INSERT INTO room_types (type_name, base_price, capacity, description) VALUES 
('標準單人房', 1500.00, 1, '適合背包客的舒適空間'),
('豪華雙人房', 2800.00, 2, '寬敞空間與城市景觀'),
('家庭套房', 4500.00, 4, '兩張雙人床，適合全家出遊');

-- 避免重複插入錯誤，使用 ON CONFLICT (如果 PostgreSQL 版本較舊可忽略這行，直接執行一次就好)
INSERT INTO rooms (room_number, type_id) VALUES 
('101', 1), ('102', 1), 
('201', 2), ('202', 2), ('203', 2),
('301', 3);
