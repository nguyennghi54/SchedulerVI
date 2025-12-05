import streamlit as st
import pandas as pd
from nlp import *
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import subprocess
import sys
from ics import Calendar, Event as IcsEvent
from streamlit_calendar import calendar

# ==========================================
# DATABASE MANAGER
# ==========================================
def start_background_worker():
    # Kiểm tra xem worker đã chạy chưa (cách đơn giản là dùng file lock hoặc session state giả lập)
    # Tuy nhiên, với Streamlit mỗi lần rerun code chạy lại, nên ta dùng biến toàn cục sys.modules để check tạm

    if not hasattr(st.session_state, 'worker_running'):
        # Gọi subprocess chạy file worker.py độc lập
        # Popen là non-blocking (không làm treo web)
        subprocess.Popen([sys.executable, "worker.py"])
        st.session_state.worker_running = True
        print("🚀 Đã khởi động Background Worker!")


start_background_worker()
class Database:
    def __init__(self, db_name="scheduler.db"):
        self.db_name = db_name

    def get_connection(self):
        # Streamlit chạy đa luồng, cần check_same_thread=False
        return sqlite3.connect(self.db_name, check_same_thread=False)

    def create_table(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    location TEXT,
                    reminder_minutes INTEGER,
                    is_notified INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def add_event(self, name, start, end, loc, remind):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (event, start_time, end_time, location, reminder_minutes)
                VALUES (?, ?, ?, ?, ?)
            """, (name, start, end, loc, remind))
            conn.commit()

    def get_all_events(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Sắp xếp theo thời gian bắt đầu thay vì ID để dễ nhìn
            cursor.execute("SELECT * FROM events ORDER BY start_time ASC")
            return cursor.fetchall()

    def delete_event(self, event_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
            conn.commit()

    def update_event(self, record_id, name, start, end, loc, remind):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Reset is_notified = 0 khi sửa để báo lại
            cursor.execute("""
                UPDATE events
                SET event=?, start_time=?, end_time=?, location=?, reminder_minutes=?, is_notified=0
                WHERE id=?
            """, (name, start, end, loc, remind, record_id))
            conn.commit()

    def mark_notified(self, event_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE events SET is_notified = 1 WHERE id = ?", (event_id,))
            conn.commit()

    def check_overlap(self, new_start_str, exclude_id=None):
        if not new_start_str: return False, None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT id, event, start_time FROM events WHERE id != ?"
            params = [exclude_id if exclude_id else -1]
            cursor.execute(query, params)
            rows = cursor.fetchall()
            for row in rows:
                _, e_name, e_start = row
                if new_start_str == e_start:
                    return True, e_name
            return False, None


# ==========================================
# 2. CONFIG & INIT
# ==========================================
st.set_page_config(page_title="AI Scheduler", page_icon="📅", layout="wide")

# Khởi tạo Session State
if 'db' not in st.session_state:
    st.session_state.db = Database()
    st.session_state.db.create_table()

if 'scheduler' not in st.session_state:
    st.session_state.scheduler = SchedulerMain()

if 'selected_id_from_table' not in st.session_state:
    st.session_state.selected_id_from_table = None

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def check_reminders():
    """Kiểm tra nhắc nhở mỗi khi app reload"""
    events = st.session_state.db.get_all_events()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    for ev in events:
        eid, name, start, end, loc, remind, notified = ev
        if notified == 1: continue

        try:
            # Xử lý datetime (có giây hoặc không)
            try:
                s_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                s_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")

            # Quy về phút
            s_dt = s_dt.replace(second=0, microsecond=0)
            remind_val = remind if remind else 0
            remind_dt = s_dt - timedelta(minutes=remind_val)
            remind_str = remind_dt.strftime("%Y-%m-%d %H:%M")

            # So sánh
            if now_str == remind_str:
                # Hiển thị Toast Notification (Góc phải màn hình)
                msg = f"🔔 Sắp diễn ra: {name}"
                if loc: msg += f" tại {loc}"
                st.toast(msg, icon="⏰")

                # Cập nhật DB
                st.session_state.db.mark_notified(eid)
        except Exception as e:
            continue


# Gọi hàm check reminder ngay đầu script
check_reminders()

# --- HÀM XUẤT FILE ---
def generate_ics(events):
    c = Calendar()
    for ev in events:
        e = IcsEvent()
        e.name = ev[1]
        # ICS yêu cầu format ISO 8601
        try:
            s_dt = pd.to_datetime(ev[2])
            e.begin = s_dt.isoformat()
            if ev[3]:
                e_dt = pd.to_datetime(ev[3])
                e.end = e_dt.isoformat()
            else:
                e.duration = timedelta(hours=1) # Default duration
            if ev[4]: e.location = ev[4]
            c.events.add(e)
        except: continue
    return str(c)

def generate_json(events):
    data = []
    for ev in events:
        data.append({
            "id": ev[0], "event": ev[1], "start": ev[2],
            "end": ev[3], "location": ev[4], "remind": ev[5]
        })
    return json.dumps(data, ensure_ascii=False, indent=2)

# ==========================================
# 4. UI LAYOUT
# ==========================================
st.title("Ứng dụng Quản lý Lịch trình cá nhân")
# --- SIDEBAR ---
with st.sidebar:
    st.header("📝 Thêm Sự Kiện")
    raw_text = st.text_area("Nhập câu lệnh:", height=100,
                            placeholder="Họp team tại P302 lúc 14h30 chiều mai...")

    if st.button("Phân Tích & Thêm", type="primary", use_container_width=True):
        if raw_text.strip():
            result = st.session_state.scheduler.process(raw_text)
            try:
                dt = datetime.strptime(result['start_time'], "%Y-%m-%d %H:%M")
                result['start_time'] = dt.strftime("%Y-%m-%d %H:%M:00")
            except:
                pass

            # Auto End
            if not result['end_time'] and result['start_time']:
                try:
                    s_dt = datetime.strptime(result['start_time'], "%Y-%m-%d %H:%M:%S")
                    result['end_time'] = (s_dt + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass

            is_overlap, conflict = st.session_state.db.check_overlap(result['start_time'])
            if is_overlap:
                st.error(f"⚠️ Trùng lịch với: '{conflict}'")
            else:
                st.session_state.db.add_event(
                    result['event'], result['start_time'], result['end_time'],
                    result['location'], result['reminder_minutes']
                )
                st.success(f"Đã thêm: {result['event']}")
                time.sleep(1)
                st.rerun()

    st.divider()
    st.header("📤 Xuất Dữ Liệu")
    events_raw = st.session_state.db.get_all_events()

    c1, c2 = st.columns(2)
    with c1:
        if events_raw:
            ics_data = generate_ics(events_raw)
            st.download_button("Tải .ics", ics_data, "calendar.ics", "text/calendar", use_container_width=True)
    with c2:
        if events_raw:
            json_data = generate_json(events_raw)
            st.download_button("Tải .json", json_data, "data.json", "application/json", use_container_width=True)

# --- MAIN CONTENT ---
tab_list, tab_calendar = st.tabs(["📋 Danh Sách & Thao Tác", "📅 Xem Lịch (Calendar View)"])

# Lấy dữ liệu mới nhất
all_events = st.session_state.db.get_all_events()
df = pd.DataFrame(all_events, columns=['ID', 'Sự Kiện', 'Bắt Đầu', 'Kết Thúc', 'Địa Điểm', 'Nhắc(p)', 'Notified'])

# --- TAB 1: DANH SÁCH (TABLE) ---
with tab_list:
    if not df.empty:
        # 1. Bảng tương tác (Có thể click chọn dòng)
        st.caption("💡 Mẹo: Click vào đầu dòng để chọn sự kiện cần Xóa/Sửa")

        # Cấu hình hiển thị
        df_display = df.drop(columns=['Notified']).copy()

        # SỬ DỤNG SELECTION EVENT CỦA STREAMLIT (MỚI)
        event_selection = st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",  # Khi chọn sẽ chạy lại app để cập nhật UI
            selection_mode="single-row",  # Chỉ cho chọn 1 dòng
            column_config={
                "ID": st.column_config.NumberColumn(width="small"),
                "Sự Kiện": st.column_config.TextColumn(width="medium"),
                "Bắt Đầu": st.column_config.DatetimeColumn(format="D/M/YYYY HH:mm"),
            }
        )

        # Xử lý Logic chọn dòng
        selected_row_indices = event_selection.selection.rows
        selected_db_id = None

        if selected_row_indices:
            # Lấy index dòng đang chọn -> Lấy ID từ dataframe gốc
            idx = selected_row_indices[0]
            selected_db_id = df.iloc[idx]['ID']
            st.session_state.selected_id_from_table = selected_db_id

        # KHU VỰC THAO TÁC (Chỉ hiện khi đã chọn ID)
        if st.session_state.selected_id_from_table:
            curr_id = st.session_state.selected_id_from_table

            # Lấy thông tin chi tiết của row đang chọn
            curr_row = df[df['ID'] == curr_id].iloc[0]

            st.divider()
            st.info(f"Đang thao tác với sự kiện: **{curr_row['Sự Kiện']}** (ID: {curr_id})")

            col_act1, col_act2 = st.columns([1, 1])

            # Nút Xóa
            if col_act1.button("🗑 Xóa Sự Kiện Này", type="primary", use_container_width=True):
                st.session_state.db.delete_event(curr_id)
                st.session_state.selected_id_from_table = None  # Reset
                st.toast("Đã xóa thành công!", icon="✅")
                time.sleep(1)
                st.rerun()

            # Form Sửa (Expand)
            with st.expander("✏️ Chỉnh Sửa Thông Tin", expanded=True):
                with st.form("edit_form"):
                    new_name = st.text_input("Tên sự kiện", value=curr_row['Sự Kiện'])
                    c_d, c_t = st.columns(2)

                    # Parse Start
                    try:
                        dt_s = pd.to_datetime(curr_row['Bắt Đầu'])
                    except:
                        dt_s = datetime.now()
                    d_s = c_d.date_input("Ngày bắt đầu", value=dt_s.date())
                    t_s = c_t.time_input("Giờ bắt đầu", value=dt_s.time())

                    # Parse End
                    try:
                        dt_e = pd.to_datetime(curr_row['Kết Thúc'])
                    except:
                        dt_e = dt_s
                    d_e = c_d.date_input("Ngày kết thúc", value=dt_e.date())
                    t_e = c_t.time_input("Giờ kết thúc", value=dt_e.time())

                    new_loc = st.text_input("Địa điểm", value=curr_row['Địa Điểm'] if curr_row['Địa Điểm'] else "")
                    new_remind = st.number_input("Nhắc trước (phút)", value=int(curr_row['Nhắc(p)']))

                    if st.form_submit_button("Lưu Thay Đổi"):
                        str_s = f"{d_s} {t_s}"
                        str_e = f"{d_e} {t_e}"
                        if len(str_s.split(":")) == 2: str_s += ":00"
                        if len(str_e.split(":")) == 2: str_e += ":00"

                        if str_s > str_e:
                            st.error("Ngày kết thúc sai!")
                        else:
                            is_ov, conf = st.session_state.db.check_overlap(str_s, exclude_id=curr_id)
                            if is_ov: st.warning(f"Trùng lịch: {conf}")

                            st.session_state.db.update_event(curr_id, new_name, str_s, str_e, new_loc, new_remind)
                            st.session_state.selected_id_from_table = None
                            st.success("Đã cập nhật!")
                            time.sleep(1)
                            st.rerun()
    else:
        st.info("Danh sách trống.")

# --- TAB 2: CALENDAR VIEW (LỊCH TRỰC QUAN) ---
with tab_calendar:
    if not df.empty:
        # Chuẩn bị dữ liệu cho thư viện Calendar
        calendar_events = []
        for _, row in df.iterrows():
            # Calendar lib cần format ISO
            try:
                s_iso = pd.to_datetime(row['Bắt Đầu']).isoformat()
                e_iso = pd.to_datetime(row['Kết Thúc']).isoformat() if row['Kết Thúc'] else s_iso

                calendar_events.append({
                    "title": f"{row['Sự Kiện']} ({row['Địa Điểm'] or ''})",
                    "start": s_iso,
                    "end": e_iso,
                    "backgroundColor": "#FF6C6C" if row['Nhắc(p)'] > 0 else "#3788d8",
                    "borderColor": "#FF6C6C" if row['Nhắc(p)'] > 0 else "#3788d8",
                })
            except:
                continue

        # Cấu hình Calendar
        calendar_options = {
            "editable": "false",  # Không cho kéo thả trực tiếp để tránh lỗi logic phức tạp
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek,timeGridDay,listWeek"
            },
            "initialView": "dayGridMonth",
            "slotMinTime": "06:00:00",
            "slotMaxTime": "22:00:00",
        }

        # Hiển thị
        calendar(events=calendar_events, options=calendar_options, custom_css="""
            .fc-event-title {font-weight: bold;}
        """)
    else:
        st.info("Chưa có dữ liệu để hiển thị lịch.")