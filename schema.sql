-- 如果表格已存在則不重複建立 (方便重複執行)
-- 因為 rooms 依賴 room_types，reservations 依賴 rooms 和 guests
-- 所以必須先建立「被參考」的表 (room_types, guests)，最後才建 reservations

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
-- 核心交易表，連結了「誰」(guest_id) 訂了「哪間房」(room_id) 在「什麼時候」
CREATE TABLE IF NOT EXISTS reservations (
    reservation_id SERIAL PRIMARY KEY,
    guest_id INT NOT NULL REFERENCES guests(guest_id), -- FK: 確保訂房的人一定存在於 guests 表
    room_id INT NOT NULL REFERENCES rooms(room_id), -- FK: 確保訂的房間一定存在於 rooms 表
    check_in_date DATE NOT NULL,
    check_out_date DATE NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'Confirmed', -- 狀態：Confirmed, Cancelled, CheckedIn
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 自動記錄這筆資料建立的時間
);

