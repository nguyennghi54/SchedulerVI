import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import time
from streamlit_calendar import calendar

# Import logic NLP
try:
    from nlp import SchedulerMain
except ImportError:
    st.error("⚠️ Lỗi: Không tìm thấy file nlp.py. Hãy đảm bảo đã upload lên GitHub.")
    st.stop()

# ==========================================
# 1. DATABASE MANAGER
# ==========================================
class Database:
    def __init__(self, db_name="scheduler.db"):
        self.db_name = db_name

    def get_connection(self):
        # Kết nối trực tiếp mỗi lần gọi để tránh lỗi cache
        return sqlite3.connect(self.db_name, check_same_thread=False)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Cấu trúc bảng chuẩn: cột tên là 'event'
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

    def get_all_events(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events ORDER BY start_time ASC")
            return cursor.fetchall()
            
    def get_unnotified_events(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events WHERE is_notified = 0")
            return cursor.fetchall()

    def add_event(self, name, start, end, loc, remind):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (event, start_time, end_time, location, reminder_minutes) 
                VALUES (?, ?, ?, ?, ?)
            """, (name, start, end, loc, remind))
            conn.commit()

    def delete_event(self, event_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
            conn.commit()

    def update_event(self, record_id, name, start, end, loc, remind):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Reset is_notified về 0 khi sửa để báo lại
            # Cột là 'event', KHÔNG PHẢI 'event_name'
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

# Khởi tạo DB
db = Database()
db.init_db()

@st.cache_resource
def get_scheduler_logic():
    return SchedulerMain()

scheduler = get_scheduler_logic()

# ==========================================
# 2. CONFIG & STATE
# ==========================================
st.set_page_config(page_title="AI Smart Scheduler", page_icon="📅", layout="wide")

if 'selected_id_from_table' not in st.session_state:
    st.session_state.selected_id_from_table = None

# Hàm kiểm tra nhắc nhở (Toast)
def check_reminders():
    events = db.get_unnotified_events()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    for ev in events:
        eid, name, start, end, loc, remind, notified = ev
        try:
            try: s_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
            except: s_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
            
            s_dt = s_dt.replace(second=0)
            remind_val = remind if remind else 0
            remind_dt = s_dt - timedelta(minutes=remind_val)
            
            if now_str == remind_dt.strftime("%Y-%m-%d %H:%M"):
                st.toast(f"🔔 {name} ({loc or 'Online'})", icon="⏰")
                db.mark_notified(eid)
        except: continue

check_reminders()

# ==========================================
# 3. UI LAYOUT
# ==========================================
st.title("🤖 Ứng dụng Quản lý Lịch trình AI")

# --- SIDEBAR ---
with st.sidebar:
    st.header("📝 Thêm Sự Kiện")
    raw_text = st.text_area("Nhập câu lệnh:", height=100, 
                            placeholder="VD: Họp team tại P302 lúc 14h30 chiều mai...")
    
    if st.button("Phân Tích & Thêm", type="primary", use_container_width=True):
        if raw_text.strip():
            with st.spinner("Đang xử lý..."):
                result = scheduler.process(raw_text)
                
                try:
                    dt = datetime.strptime(result['start_time'], "%Y-%m-%d %H:%M")
                    result['start_time'] = dt.strftime("%Y-%m-%d %H:%M:00")
                except: pass
                
                if not result['end_time'] and result['start_time']:
                     try:
                        s = datetime.strptime(result['start_time'], "%Y-%m-%d %H:%M:%S")
                        result['end_time'] = (s + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
                     except: pass

                is_overlap, conflict = db.check_overlap(result['start_time'])
                if is_overlap:
                    st.error(f"⚠️ Trùng lịch với: '{conflict}'")
                else:
                    db.add_event(
                        result['event'], result['start_time'], result['end_time'], 
                        result['location'], result['reminder_minutes']
                    )
                    st.success(f"Đã thêm: {result['event']}")
                    time.sleep(0.5)
                    st.rerun()

# --- TABS ---
tab_list, tab_calendar = st.tabs(["📋 Danh Sách & Thao Tác", "📅 Xem Lịch"])

# Lấy dữ liệu mới nhất
all_events = db.get_all_events()
df = pd.DataFrame(all_events, columns=['ID', 'Sự Kiện', 'Bắt Đầu', 'Kết Thúc', 'Địa Điểm', 'Nhắc(p)', 'Notified'])

# --- TAB 1: DANH SÁCH ---
with tab_list:
    if not df.empty:
        st.caption("👇 Click vào dòng để hiện menu Xóa/Sửa")
        
        event_selection = st.dataframe(
            df.drop(columns=['Notified']),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"data_table_{len(df)}", # Key dynamic để ép vẽ lại khi số lượng đổi
            column_config={
                "ID": st.column_config.NumberColumn(width="small"),
                "Sự Kiện": st.column_config.TextColumn(width="medium"),
            }
        )
        
        selected_rows = event_selection.selection.rows
        if selected_rows:
            st.session_state.selected_id_from_table = df.iloc[selected_rows[0]]['ID']
        
        # --- ACTION PANEL ---
        if st.session_state.selected_id_from_table:
            curr_id = st.session_state.selected_id_from_table
            check_exists = df[df['ID'] == curr_id]
            
            if not check_exists.empty:
                curr_row = check_exists.iloc[0]
                st.divider()
                st.info(f"Đang thao tác: **{curr_row['Sự Kiện']}** (ID: {curr_id})")
                
                c1, c2 = st.columns(2)
                
                # --- HÀM XỬ LÝ XÓA (FIXED) ---
                def delete_handler():
                    # 1. Xóa trong DB
                    db.delete_event(curr_id)
                    # 2. Reset State (Quan trọng)
                    st.session_state.selected_id_from_table = None
                    # 3. Thông báo
                    st.toast("✅ Đã xóa thành công!")
                    # 4. KHÔNG GỌI ST.RERUN() Ở ĐÂY. Streamlit tự rerun sau callback.
                    
                c1.button("🗑 Xóa Sự Kiện", type="primary", use_container_width=True, on_click=delete_handler)
                
                # --- FORM SỬA ---
                with st.expander("✏️ Chỉnh Sửa", expanded=True):
                    with st.form("edit_form"):
                        new_name = st.text_input("Tên", value=curr_row['Sự Kiện'])
                        
                        try: dt_s = pd.to_datetime(curr_row['Bắt Đầu'])
                        except: dt_s = datetime.now()
                        d_s = st.date_input("Ngày bắt đầu", value=dt_s.date())
                        t_s = st.time_input("Giờ bắt đầu", value=dt_s.time())

                        try: dt_e = pd.to_datetime(curr_row['Kết Thúc'])
                        except: dt_e = dt_s
                        d_e = st.date_input("Ngày kết thúc", value=dt_e.date())
                        t_e = st.time_input("Giờ kết thúc", value=dt_e.time())
                        
                        new_loc = st.text_input("Địa điểm", value=curr_row['Địa Điểm'] or "")
                        new_remind = st.number_input("Nhắc trước (p)", value=int(curr_row['Nhắc(p)']))

                        if st.form_submit_button("Lưu Thay Đổi"):
                            str_s = f"{d_s} {t_s}"
                            str_e = f"{d_e} {t_e}"
                            if len(str_s.split(":"))==2: str_s += ":00"
                            if len(str_e.split(":"))==2: str_e += ":00"
                            
                            db.update_event(curr_id, new_name, str_s, str_e, new_loc, new_remind)
                            st.success("Đã cập nhật!")
                            time.sleep(0.5)
                            st.rerun() # Form submit thì cần rerun thủ công
            else:
                st.session_state.selected_id_from_table = None
                st.rerun()
    else:
        st.info("Danh sách trống.")

# --- TAB 2: CALENDAR ---
with tab_calendar:
    if not df.empty:
        calendar_events = []
        for _, row in df.iterrows():
            if not row['Bắt Đầu']: continue
            try:
                s_dt = pd.to_datetime(row['Bắt Đầu'])
                s_iso = s_dt.isoformat()
                
                e_iso = s_iso
                if row['Kết Thúc']:
                    e_dt = pd.to_datetime(row['Kết Thúc'])
                    if not pd.isna(e_dt): e_iso = e_dt.isoformat()
                
                color = "#FF6C6C" if row['Nhắc(p)'] > 0 else "#3788d8"
                
                calendar_events.append({
                    "title": row['Sự Kiện'],
                    "start": s_iso,
                    "end": e_iso,
                    "backgroundColor": color,
                    "borderColor": color
                })
            except: continue

        mode = st.radio("Chế độ xem:", ["Tháng", "Tuần", "Ngày", "Danh sách"], horizontal=True)
        view_map = {"Tháng": "dayGridMonth", "Tuần": "timeGridWeek", "Ngày": "timeGridDay", "Danh sách": "listWeek"}
        
        calendar_options = {
            "headerToolbar": {
                "left": "today prev,next",
                "center": "title",
                "right": ""
            },
            "initialView": view_map[mode],
            "navLinks": True,
            "selectable": True,
            "nowIndicator": True,
        }
        
        # Key dynamic để ép render lại khi dữ liệu thay đổi
        calendar(events=calendar_events, options=calendar_options, key=f"cal_{mode}_{len(df)}_{time.time()}")
    else:
        st.info("Chưa có dữ liệu lịch.")

# ==========================================
# 4. DEBUG DASHBOARD (ADMIN)
# ==========================================
with st.sidebar:
    st.divider()
    with st.expander("🛠 Debug Tools"):
        import os
        st.write(f"DB Path: `{os.path.abspath('scheduler.db')}`")
        if st.button("Reload App"):
            st.rerun()
        
        # Download DB
        try:
            with open("scheduler.db", "rb") as fp:
                st.download_button("📥 Tải Database", fp, "scheduler_debug.db")
        except: pass
