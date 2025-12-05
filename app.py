# @title DATABASE & UI
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from nlp import *

# ==========================================
# DATABASE MANAGER
# ==========================================
class Database:
    def __init__(self, db_name="scheduler.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_table()

    # Khởi tạo bảng
    def create_table(self):
        self.cursor.execute("""
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
        self.conn.commit()

    # Thêm event
    def add_event(self, name, start, end, loc, remind):
        self.cursor.execute("""
            INSERT INTO events (event, start_time, end_time, location, reminder_minutes)
            VALUES (?, ?, ?, ?, ?)
        """, (name, start, end, loc, remind))
        self.conn.commit()

    # Xếp theo ID
    def get_all_events(self):
        self.cursor.execute("SELECT * FROM events ORDER BY id ASC")
        return self.cursor.fetchall()

    # Đánh dấu event đã thông báo
    def mark_notified(self, event_id):
        self.cursor.execute("UPDATE events SET is_notified = 1 WHERE id = ?", (event_id,))
        self.conn.commit()

    # Xóa event
    def delete_event(self, event_id):
        self.cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
        self.conn.commit()

    # Sửa event
    def update_event(self, record_id, name, start, end, loc, remind):
        self.cursor.execute("""
            UPDATE events
            SET event=?, start_time=?, end_time=?, location=?, reminder_minutes=?, is_notified=0
            WHERE id=?
        """, (name, start, end, loc, remind, record_id))
        self.conn.commit()

    # Kiểm tra trùng lặp tgian bắt đầu event
    def check_overlap(self, new_start_str, new_end_str, exclude_id=None):
        if not new_start_str: return False, None
        # Lấy ds các event khác id
        query = "SELECT id, event, start_time FROM events WHERE id != ?"
        params = [exclude_id if exclude_id else -1]
        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()
        for row in rows:
            _, e_name, e_start = row
            if new_start_str == e_start:
                return True, e_name  # trùng lịch
        return False, None # an toàn

    # Kiểm tra cú pháp datetime chuẩn
    def check_valid_datetime(date_text):
        try:
            if not date_text: return False
            datetime.strptime(date_text, "%Y-%m-%d %H:%M:%S")
            return True
        except ValueError:
            return False


# ==========================================
# UI LOGIC
# ==========================================
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.widgets import DateEntry

class SchedulerApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Ứng dụng quản lý lịch trình cá nhân AI")
        self.geometry("1200x800")
        style = ttk.Style()
        style.configure("Treeview", font=("Segoe UI", 11))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        self.db = Database()
        self.setup_ui()
        self.load_data()

        # Start background thread
        self.stop_thread = False
        self.thread = threading.Thread(target=self.background_checker, daemon=True)
        self.thread.start()

    #--TẠO UI---
    def setup_ui(self):
        # --INPUT AREA (top)--
        input_frame = ttk.Labelframe(self, padding=15)
        input_frame.pack(fill=X, padx=10, pady=5)
        # Placeholder text
        self.entry_var = tk.StringVar()
        self.entry_task = ttk.Entry(input_frame, textvariable=self.entry_var, font=("Segoe UI", 11))
        self.entry_task.pack(side=LEFT, padx=5, fill=X, expand=True)
        self.placeholder_text = "Họp team marketing tại P302 lúc 14h30 chiều mai, nhắc trước 30p"
        self.entry_task.insert(0, self.placeholder_text)
        # Button thêm event
        btn_add = ttk.Button(input_frame, text="Phân tích & Thêm", command=self.process_input, bootstyle=SUCCESS)
        btn_add.pack(side=LEFT, padx=5)

        # --LIST AREA (middle)--
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        # Tạo bảng lịch
        cols = ("ID", "Sự Kiện", "Bắt Đầu", "Kết Thúc", "Địa Điểm", "Nhắc Trước")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", bootstyle="info", height=20)
        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)

        # Định nghĩa các cột
        self.tree.heading("ID", text="ID");
        self.tree.column("ID", width=40, stretch=False, anchor=CENTER)
        self.tree.heading("Sự Kiện", text="Nội Dung Sự Kiện")
        self.tree.column("Sự Kiện", anchor=W)
        self.tree.heading("Bắt Đầu", text="Bắt Đầu")
        self.tree.column("Bắt Đầu", width=140, anchor=CENTER)
        self.tree.heading("Kết Thúc", text="Kết Thúc")
        self.tree.column("Kết Thúc", width=140, anchor=CENTER)
        self.tree.heading("Địa Điểm", text="Địa Điểm")
        self.tree.column("Địa Điểm", width=150, anchor=W)
        self.tree.heading("Nhắc Trước", text="Nhắc Trước(p)")
        self.tree.column("Nhắc Trước", width=100, anchor=CENTER)

        # --BUTTON AREA (bottom)--
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=X)
        self.status_lbl = ttk.Label(btn_frame, text="Sẵn sàng", font=("Segoe UI", 9, "italic"), bootstyle="secondary")
        self.status_lbl.pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="Xóa Event chọn", command=self.delete_selected, bootstyle=DANGER).pack(side=RIGHT)
        ttk.Button(btn_frame, text="Làm mới", command=self.load_data, bootstyle=SECONDARY).pack(side=RIGHT, padx=10)
        ttk.Button(btn_frame, text="Sửa Event", command=self.edit_selected, bootstyle=WARNING).pack(side=RIGHT, padx=5)

    #--XỬ LÝ USER INPUT--
    def process_input(self):
        raw_text = self.entry_task.get()
        if not raw_text: return
        # --KẾT QUẢ TỪ MODULE--
        scheduler = SchedulerMain()
        result = scheduler.process(raw_text)
        try:
            # Nếu datetime HH:MM, cộng thêm s
            dt = datetime.strptime(result['start_time'], "%Y-%m-%d %H:%M")
            result['start_time'] = dt.strftime("%Y-%m-%d %H:%M:%00")
        except ValueError:
            try:
                dt = datetime.strptime(result['start_time'], "%Y-%m-%d %H:%M:%S")
                result['start_time'] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        # nếu null end = start +1h
        if not result['end_time'] and result['start_time']:
            try:
                s_dt = datetime.strptime(result['start_time'], "%Y-%m-%d %H:%M:%S")
                result['end_time'] = (s_dt + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass

        extracted_data = {
            "event": result['event'],
            "start": result['start_time'],
            "end": result['end_time'],
            "loc": result['location'],
            "remind": result['reminder_minutes']
        }
        # Lưu vào DB
        self.db.add_event(
            extracted_data["event"],
            extracted_data["start"],
            extracted_data["end"],
            extracted_data["loc"],
            extracted_data["remind"]
        )
        self.entry_task.delete(0, END)
        self.load_data()
        print("Đã thêm sự kiện!")

    def load_data(self):
        # Xóa cũ
        for row in self.tree.get_children():
            self.tree.delete(row)
        # Load lại db
        rows = self.db.get_all_events()
        for row in rows:
            # row: (id, name, start, end, loc, remind, notified)
            self.tree.insert("", END, values=row[:6])

    #Chọn để xóa
    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Chú ý", "Vui lòng chọn dòng để xóa!")
            return
        if selected:
            item = self.tree.item(selected[0])
            record_id = item['values'][0]
            self.db.delete_event(record_id)
            self.load_data()

    # Chọn để sửa
    def edit_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Chú ý", "Vui lòng chọn dòng để sửa!")
            return
        values = self.tree.item(selected[0])['values']
        rec_id = values[0]
        # Tách datetime để sửa riêng (date dùng DatePicker)
        def split_dt(dt_str):
            try:
                if not dt_str or dt_str == 'None': raise ValueError
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
            except:
                return datetime.now().strftime("%Y-%m-%d"), "00:00"
        s_date, s_time = split_dt(values[2])
        e_date, e_time = split_dt(values[3])

        # --- TẠO POPUP ---
        win = ttk.Toplevel(self)
        win.title("Chỉnh Sửa Sự Kiện")
        win.geometry("550x600")
        # Thêm biến lưu trữ DateEntry
        self.temp_de_start = None
        self.temp_de_end = None
        content = ttk.Frame(win, padding=20)
        content.pack(fill=BOTH, expand=True)

        # 1. Tên
        ttk.Label(content, text="Tên sự kiện:", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        ent_name = ttk.Entry(content, width=50)
        ent_name.pack(fill=X, pady=(5, 15))
        ent_name.insert(0, values[1])

        # 2. Start Time
        ttk.Label(content, text="Bắt đầu:", font=("Segoe UI", 10, "bold"), bootstyle="primary").pack(anchor=W)
        f_start = ttk.Frame(content);
        f_start.pack(fill=X, pady=(5, 15))

        # 3. Start time
        self.temp_de_start = DateEntry(f_start, dateformat='%Y-%m-%d', startdate=datetime.strptime(s_date, "%Y-%m-%d"),
                                       width=15, bootstyle="primary")
        self.temp_de_start.pack(side=LEFT, padx=(0, 10))
        te_start = ttk.Entry(f_start, width=10);
        te_start.insert(0, s_time);
        te_start.pack(side=LEFT)
        ttk.Label(f_start, text="(Giờ:Phút)").pack(side=LEFT, padx=5)

        # 4. End time
        ttk.Label(content, text="Kết thúc:", font=("Segoe UI", 10, "bold"), bootstyle="primary").pack(anchor=W)
        f_end = ttk.Frame(content);
        f_end.pack(fill=X, pady=(5, 15))
        self.temp_de_end = DateEntry(f_end, dateformat='%Y-%m-%d', startdate=datetime.strptime(e_date, "%Y-%m-%d"),
                                     width=15, bootstyle="primary")
        self.temp_de_end.pack(side=LEFT, padx=(0, 10))
        te_end = ttk.Entry(f_end, width=10);
        te_end.insert(0, e_time);
        te_end.pack(side=LEFT)

        # 5. Location & Reminder
        ttk.Label(content, text="Địa điểm:", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        ent_loc = ttk.Entry(content);
        ent_loc.pack(fill=X, pady=(5, 15))
        ent_loc.insert(0, values[4] if values[4] else "")
        ttk.Label(content, text="Nhắc trước (phút):", font=("Segoe UI", 10, "bold")).pack(anchor=W)
        # Nếu remind null
        remind_val = str(values[5]).replace(" phút", "").replace("-", "0")
        if remind_val == 'None': remind_val = "0"
        ent_remind = ttk.Entry(content);
        ent_remind.pack(fill=X, pady=(5, 20))
        ent_remind.insert(0, remind_val)

        # Hàm lưu thay đổi
        def save_changes():
            try:
                # Lấy ngày từ DateEntry + giờ từ Entry
                d_start = self.temp_de_start.entry.get()
                d_end = self.temp_de_end.entry.get()
                t_start = te_start.get().strip()
                t_end = te_end.get().strip()
                # tự thêm :00 nếu null
                if len(t_start.split(':')) == 2: t_start += ":00"
                if len(t_end.split(':')) == 2: t_end += ":00"
                new_start = f"{d_start} {t_start}"
                new_end = f"{d_end} {t_end}"
                name = ent_name.get()
                loc = ent_loc.get()
                remind = ent_remind.get()

                print(f"DEBUG: Trying to save: {new_start} -> {new_end}")  # In ra terminal để check
                # Validate format
                try:
                    datetime.strptime(new_start, "%Y-%m-%d %H:%M:%S")
                    datetime.strptime(new_end, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    messagebox.showerror("Lỗi format",
                                         f"Ngày giờ không hợp lệ!\nFormat: YYYY-MM-DD HH:MM\nBạn nhập: {new_start}")
                    return
                if new_start > new_end:
                    messagebox.showerror("Lỗi logic", "Ngày kết thúc phải sau ngày bắt đầu!")
                    return

                # Check trùng start time
                is_overlap, conflict = self.db.check_overlap(new_start, new_end, exclude_id=rec_id)
                if is_overlap:
                    if not messagebox.askyesno("Cảnh báo trùng",
                                               f"Thời gian này trùng với sự kiện:\n'{conflict}'\nVẫn muốn lưu?"): return

                # Lưu vào DB
                self.db.update_event(rec_id, name, new_start, new_end, loc, remind)
                # Refresh UI
                self.load_data()
                self.status_lbl.config(text="Đã cập nhật sự kiện", bootstyle="success")
                win.destroy()
                messagebox.showinfo("Thành công", "Đã lưu thay đổi!")

            except Exception as e:
                import traceback
                err_msg = traceback.format_exc()
                print(err_msg)
                messagebox.showerror("Lỗi system", f"Không thể lưu!\nChi tiết lỗi:\n{e}")

        # Nút Lưu
        ttk.Button(content, text="LƯU THAY ĐỔI", command=save_changes, bootstyle="success").pack(fill=X, ipady=5)

    # ==========================================
    # THREAD NHẮC NHỞ
    # ==========================================
    def background_checker(self):
        print("Service Started...")
        while True:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            events = self.db.get_all_events()
            for ev in events:
                eid, name, start, end, loc, remind, notified = ev
                if notified == 1: continue
                try:
                    events = self.db.get_all_events()
                    for ev in events:
                        eid, name, start, end, loc, remind, notified = ev
                        # Bỏ qua nếu event đã được báo
                        if notified == 1: continue
                        # Parse time
                        s_dt = None
                        try:
                            # Có giây
                            s_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
                        except ValueError:
                            try:
                                # data cũ thiếu giây
                                s_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                continue  # Data lỗi
                        # --TÍNH GIỜ NHẮC--
                        s_dt = s_dt.replace(second=0, microsecond=0)
                        remind_minutes = remind if remind else 0
                        remind_dt = s_dt - timedelta(minutes=remind_minutes)
                        remind_str = remind_dt.strftime("%Y-%m-%d %H:%M")
                        if now_str == remind_str:
                            # Cập nhật DB trước khi hiện popup
                            self.db.mark_notified(eid)
                            self.after(0, lambda n=name, l=loc, t=remind_minutes: self.show_reminder_popup(n, l, t))
                            self.after(1000, self.load_data) # Refresh lại icon trên bảng

                except Exception as e:
                    print(f"Checker Error: {e}")

            time.sleep(20)  # Check mỗi 20s

    # --POPUP UI--
    def show_reminder_popup(self, name, loc, minutes):
        msg = f"SỰ KIỆN: {name}\n"
        if loc: msg += f"TẠI: {loc}\n"
        if minutes > 0:
            msg += f"(Nhắc trước {minutes} phút)"
        else:
            msg += "ĐÃ ĐẾN GIỜ!"
        messagebox.showinfo("NHẮC LỊCH TRÌNH", msg)

import os, signal
if __name__ == "__main__":
    def on_closing():
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            app.quit()
            app.destroy()
    app = SchedulerApp()
    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()