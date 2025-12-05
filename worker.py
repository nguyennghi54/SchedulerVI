import time
import sqlite3
from datetime import datetime, timedelta
from plyer import notification  # Thư viện bắn thông báo Windows/Mac/Linux


def check_reminders():
    print("Worker: Đang chạy ngầm tìm lịch...")
    # Kết nối DB riêng (Vì worker là tiến trình khác)
    conn = sqlite3.connect("scheduler.db")
    cursor = conn.cursor()

    while True:
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            # Lấy các sự kiện chưa báo
            cursor.execute("SELECT id, event, start_time, location, reminder_minutes FROM events WHERE is_notified = 0")
            events = cursor.fetchall()

            for ev in events:
                eid, name, start, loc, remind = ev

                # Xử lý thời gian (copy logic cũ)
                try:
                    s_dt = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                except:
                    try:
                        s_dt = datetime.strptime(start, "%Y-%m-%d %H:%M")
                    except:
                        continue

                s_dt = s_dt.replace(second=0)
                remind_val = remind if remind else 0
                remind_dt = s_dt - timedelta(minutes=remind_val)
                remind_str = remind_dt.strftime("%Y-%m-%d %H:%M")

                if now_str == remind_str:
                    # 1. BẮN THÔNG BÁO HỆ THỐNG (OS LEVEL)
                    msg = f"{name}"
                    if loc: msg += f" tại {loc}"

                    notification.notify(
                        title='📅 NHẮC LỊCH TRÌNH AI',
                        message=msg,
                        app_icon=None,  # Bạn có thể để đường dẫn file .ico
                        timeout=10,  # Hiện trong 10 giây
                    )

                    # 2. Update DB
                    cursor.execute("UPDATE events SET is_notified = 1 WHERE id = ?", (eid,))
                    conn.commit()
                    print(f"Worker: Đã báo sự kiện {name}")

        except Exception as e:
            print(f"Lỗi Worker: {e}")

        time.sleep(20)  # Check mỗi 20s


if __name__ == "__main__":
    check_reminders()