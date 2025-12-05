# @title TỔNG HỢP
import re
import json
from datetime import datetime, timedelta
from underthesea import ner
from scipy.stats import norm
# ==========================================
# --TIỀN XỬ LÝ--
class Preprocess:
    VI_NORM_DICT = {
        "hnay": "hôm nay",
        "toi": "tôi", "t": "tôi",
        "dc": "được", "trc": "trước",
        "ko": "không", "k": "không",
        "khong": "không", "h": "giờ",
        "bh": "bây giờ", "p": "phút",
        "cn": "chủ nhật", "t2": "thứ 2", "t3": "thứ 3", "t4": "thứ 4",
        "t5": "thứ 5", "t6": "thứ 6", "t7": "thứ 7"
    }

    @staticmethod
    def basic_clean(text):
        # Nếu không phải string
        if not isinstance(text, str): return ""
        # Chuẩn hóa sau dấu câu có whitespace
        text = re.sub(r'([.,!?;()])', r'\1 ', text)
        # Loại bỏ whitespace thừa
        text = re.sub(r'\s+', ' ', text)
        return text

    @staticmethod
    def VI_normalize(text: str):
        words = text.split()
        processed = []
        for word in words:
            processed.append(Preprocess.VI_NORM_DICT.get(word, word))
        normalized = " ".join(processed)
        return normalized

    def Text_Preprocess_Util(text):
        cleaned = Preprocess.basic_clean(text)
        normalized = Preprocess.VI_normalize(cleaned)
        return normalized


# ==========================================
# --CHUẨN HÓA THGIAN--
class TimeRangeNormalizer:
    def __init__(self):
        pass
    def fix_range(self, start_dt: datetime, end_dt: datetime):
        # Sửa end theo start nếu end<start
        if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
            return start_dt, end_dt
        if end_dt < start_dt:
            # Đồng bộ date của end theo start (giữ time)
            corrected_end_dt = end_dt.replace(
                year=start_dt.year,
                month=start_dt.month,
                day=start_dt.day
            )
            # TH như 23h->1h
            if corrected_end_dt < start_dt:
                corrected_end_dt += timedelta(days=1)
            return start_dt, corrected_end_dt

        return start_dt, end_dt  # nếu end>start
# ==========================================
# XỬ LÝ LỖI
# ==========================================

# @title Xử lý rác trong result
class CleaningJunk:

    # @title Dọn rác chuỗi event
    def clean_event_name(event_text):
        if not event_text:
            return ""
            # Stopwords đầu câu
        prefixes = [
            'nhắc', 'nhở', 'tôi', 'hãy', 'lịch', 'nhớ', 'sớm',
            'việc', 'cần', 'phải', 'tạo']
        # Các từ rác cuối câu
        trailing_junk = [
            ' deadline', ' này', ' tới', ' sau', ' trước', ' lúc',
            ' hôm nay', ' ngày mai', ' tuần', ' tuần sau', ' tuần này', ' thứ',
            ' sáng', ' chiều', ' tối', ' phút', ' giờ']
        # Giới từ thừa
        trailing_prep = [
            ' tại', ' ở', ' trên', ' trong', ' ngoài',
            ' về', ' qua', ' với', ' là', ' lúc', ' đi', ' đến', ' từ', ' cho']

        text = event_text

        # Loop làm sạch
        has_change = True
        while has_change:
            has_change = False
            original_text = text

            # xóa prefix
            for p in prefixes:
                if re.match(r'^' + p + r'\b', text, flags=re.IGNORECASE):
                    text = re.sub(r'^' + p + r'\b', '', text, flags=re.IGNORECASE).strip()
                    has_change = True
            # xóa suffix
            for junk in trailing_junk:
                if text.lower().endswith(junk):
                    text = text[:-len(junk)].strip()
                    has_change = True
            # xóa giới từ
            for prep in trailing_prep:
                if text.lower().endswith(prep):
                    text = text[:-len(prep)].strip()
                    has_change = True
            # xóa ký tự lẻ
            text = re.sub(r'\b[hHgGp]\b', ' ', text).strip()
            text = re.sub(r'\b\d{1,2}\b', ' ', text).strip()
            # xóa cụm thứ/ngày cuối câu
            weekday_pattern = r'\b(thứ|chủ nhật)\s+\w+$'
            if re.search(weekday_pattern, text, flags=re.IGNORECASE):
                text = re.sub(weekday_pattern, '', text, flags=re.IGNORECASE).strip()
                has_change = True
            # xóa số lẻ giữa
            floating_number_pattern = r'\s\d{1,2}\s'
            if re.search(floating_number_pattern, text):
                text = re.sub(floating_number_pattern, ' ', text).strip()
                text = re.sub(r'\s+', ' ', text)
                has_change = True
            # xóa số cuối câu
            if re.search(r'\s+\d{1,4}$', text):
                text = re.sub(r'\s+\d{1,4}$', '', text).strip()
                has_change = True
            text = re.sub(r'\s+', ' ', text).strip()
            if text != original_text:
                has_change = True
        return text.strip() if len(text) > 1 else "Sự kiện chung"

    # @title Dọn rác chuỗi loc
    def refine_location(loc_text):
        if not loc_text:
            return ""
        lower_text = loc_text.lower()
        # Loại location bắt đầu bằng stopword
        time_indicators = [
            'vào lúc', 'lúc', 'vào', 'hồi', 'tầm', 'khoảng', 'tối', 'sáng', 'chiều',
            'trưa', 'ngày', 'thứ', 'tháng', 'năm', 'deadline', 'h30', 'h15', 'h45', "tại"
        ]
        for indicator in time_indicators:
            if lower_text.startswith(indicator):
                return ""
        # Nếu chỉ có số -> Bỏ
        if loc_text.isdigit():
            return ""
        # TH loc dính với datetime
        cut_off_words = [' lúc ', ' vào ', ' ngày ', ' từ ', ' đến ']
        for word in cut_off_words:
            if word in lower_text:
                index = lower_text.find(word)
                loc_text = loc_text[:index].strip()  # Chỉ lấy phần trước đó
        # Loại pattern giờ còn sót
        time_pattern = r'\b\d{1,2}\s*[hHg]\s*.*'
        if re.search(time_pattern, loc_text):
            loc_text = re.sub(time_pattern, '', loc_text).strip()
        # Ký tự rác cuối câu (dấu phẩy, dấu gạch ngang)
        loc_text = loc_text.strip(' ,.-')

        return loc_text

# ==========================================
# XỬ LÝ THỜI GIAN
# ==========================================
TODAY = datetime.now()
class DateParser:
    def __init__(self, current_time=TODAY):
        self.current_time = current_time

    # Xử lý ngày tương đối
    def parse_relative_date(self, date_str):
        today = self.current_time.date()
        date_str = date_str.lower().strip()
        if date_str in ['hôm nay', 'nay']: return today
        if date_str in ['mai', 'ngày mai', 'sáng mai', 'chiều mai', 'tối mai']: return today + timedelta(days=1)
        if date_str in ['mốt', 'ngày mốt', 'ngày kia']: return today + timedelta(days=2)

        # Xử lý chuỗi có thứ (VD thứ 6 tuần sau)
        weekday_map = {'thứ 2': 0, 'thứ hai': 0, 'thứ 3': 1, 'thứ ba': 1, 'thứ 4': 2,
                       'thứ tư': 2, 'thứ 5': 3, 'thứ năm': 3, 'thứ 6': 4, 'thứ sáu': 4,
                       'thứ 7': 5, 'thứ bảy': 5, 'chủ nhật': 6, 'cn': 6}
        for key, target_weekday in weekday_map.items():
            if key in date_str:
                current_weekday = self.current_time.weekday()
                days_diff = target_weekday - current_weekday
                # Nếu có "tuần sau/tới" -> +7 ngày
                if any(x in date_str for x in ["tuần sau", "tuần tới", "tới"]):
                    return today + timedelta(days=days_diff + 7)
                # Nếu không tìm ngày gần nhất trong tương lai
                if days_diff <= 0: days_diff += 7
                return today + timedelta(days=days_diff)

        # Nếu chỉ có "tuần sau/tới" -> cũng +7 ngày
        if any(x in date_str for x in ["tuần sau", "tuần tới", "tới"]):
            return today + timedelta(days=7)

        # Xử lý chuỗi DD/MM
        match_date = re.search(r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?', date_str)
        if match_date:
            day, month = int(match_date.group(1)), int(match_date.group(2))
            year = int(match_date.group(3)) if match_date.group(3) else self.current_time.year
            if not match_date.group(3):  # Logic đoán năm
                if month < self.current_time.month:
                    year += 1
                elif month == self.current_time.month and day < self.current_time.day:
                    year += 1
            try:
                return datetime(year, month, day).date()
            except:
                pass

        return today
    # Gộp date và time
    def parse_time(self, time_str, session=None):
        h, m = 0, 0
        match = re.search(r'(\d{1,2})[:h](\d{0,2})', time_str)
        if match:
            h = int(match.group(1))
            m = int(match.group(2)) if match.group(2) else 0
        else:
            match_h = re.search(r'(\d{1,2})\s*giờ', time_str)
            if match_h: h = int(match_h.group(1))

        if session and any(s in session for s in ['chiều', 'tối', 'pm']) and h < 12: h += 12
        return h, m


# ==========================================
# HÀM LẤY LỊCH
# ==========================================
class SchedulerMain:
    def __init__(self):
        self.parser = DateParser()
        # self.cleaner = CleaningJunk()
        # RULE CHO REGEX
        # Nếu gặp các từ mở đầu loc (tại, ở..), lấy các từ ở sau, dừng khi gặp từ chỉ thgian/EoL
        self.loc_pattern = re.compile(
            r'(?:tại|ở|qua|trên|về)\s+([a-zA-Z0-9_À-ỹ\s]+?)(?=(?:\s*[\.,])?\s+(?:lúc|vào|ngày|nhắc|báo|từ|trước)|$)',
            re.IGNORECASE)
        # Format giờ: 09:30, 9h30, 9h, 9 giờ, 09:00
        self.time_pattern = re.compile(r'(\d{1,2}[:h]\d{0,2}|\d{1,2}\s*giờ(?:\s*kém\s*\d+)?)', re.IGNORECASE)
        self.date_pattern = re.compile(
            r'(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|hôm nay|nay|ngày mai|mai|mốt|ngày kia|thứ\s*\d|chủ nhật|cuối tuần|tuần sau|tuần tới)',
            re.IGNORECASE)
        # Format reminder: nhắc/báo trước/sớm X
        self.reminder_pattern = re.compile(r'(?:nhắc|báo)(?:\s+trước|\s+sớm)?\s+(\d+)\s*(phút|p|giờ|tiếng|h)',
                                           re.IGNORECASE)

    # --HÀM TRÍCH XUẤT EVENT--
    def extract_event_name(self, input, remove_list):
        clean_text = input
        # Xóa Time, Location, Reminded đã nhận diện
        for comp in remove_list:
            if comp:
                clean_text = clean_text.replace(comp, " ")
        # Xóa stopwords
        stopwords = [
            'nhắc', 'tôi', 'hãy', 'lịch', 'lúc', 'vào', 'ở', 'tại', 'trong',
            'ngày', 'sáng', 'chiều', 'tối', 'khoảng', 'tầm', 'phút', 'trước',
            'đi', 'đến', 'từ', 'có', 'buổi', 'là', 'nhớ', 'sớm'
        ]
        for word in stopwords:
            clean_text = re.sub(r'\b' + word + r'\b', ' ', clean_text, flags=re.IGNORECASE)

        clean_text = re.sub(r'[,\.\-]', ' ', clean_text)  # bỏ dấu
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()  # bỏ whitespace
        event = CleaningJunk.clean_event_name(clean_text)
        return event.strip()

    # --HÀM XỬ LÝ CHÍNH--
    def process(self, input):
        # 1. NER tìm location
        text = Preprocess.Text_Preprocess_Util(input)
        # print(processed)
        raw_NER = ner(text)
        ner_locs = []
        curr = []
        exclusion_words = ['ngày', 'sáng', 'tối', 'chiều', 'trưa']
        # B-LOC: từ đầu, I-LOC: từ kế
        for word, pos, chunk, tag in raw_NER:
            if word not in exclusion_words:
                if tag == 'B-LOC':
                    if curr: ner_locs.append(" ".join(curr))
                    curr = [word]
                elif tag == 'I-LOC':
                    curr.append(word)
                # nếu tên địa danh có số
                elif curr and (pos == 'M' or word.isdigit()):
                    curr.append(word)
                else:
                    if curr: ner_locs.append(" ".join(curr))
                    curr = []
            if curr: ner_locs.append(" ".join(curr))

        # 2. Regex extraction
        regex_locs = [m.group(1) for m in self.loc_pattern.finditer(text)]  # List lấy phần giữa regex loc
        raw_times = self.time_pattern.findall(text)
        raw_dates = self.date_pattern.findall(text)
        session = re.search(r'(sáng|trưa|chiều|tối|đêm)', text, re.IGNORECASE)
        session_val = session.group(0) if session else None
        remind_match = self.reminder_pattern.search(text)
        reminder_min = 0
        remind_str = ""
        if remind_match:  # lấy phút
            remind_str = remind_match.group(0)
            val = int(remind_match.group(1))
            unit = remind_match.group(2)
            reminder_min = val * 60 if unit in ['giờ', 'tiếng', 'h'] else val

        # 3. Hợp nhất chuỗi loc
        # Nếu NER null thì convert sang rỗng
        if ner_locs is None: ner_locs = []
        all_locs = list(set(ner_locs + regex_locs))
        clean_locs = [l.strip() for l in all_locs if len(l.strip()) > 1]  # lọc chuỗi ngắn
        if not clean_locs:
            final_loc = None
        else:
            longest_loc = max(clean_locs, key=len) if clean_locs else None
            final_loc = CleaningJunk.refine_location(longest_loc)

        # 4. Parsing
        start_dt = None
        end_dt = None

        # Mặc định datetime đầu tiên nếu ds rỗng
        date0 = raw_dates[0] if raw_dates else "hôm nay"
        time0 = raw_times[0] if raw_times else "08:00"

        # Xử lý start-end time
        # TH1: đủ 2 giờ 2 ngày
        if len(raw_times) >= 2 and len(raw_dates) >= 2:
            # Start:
            d1 = self.parser.parse_relative_date(raw_dates[0])
            h1, m1 = self.parser.parse_time(raw_times[0], session_val)
            start_dt = datetime.combine(d1, datetime.min.time()).replace(hour=h1, minute=m1)
            # End:
            d2 = self.parser.parse_relative_date(raw_dates[1])
            h2, m2 = self.parser.parse_time(raw_times[1], session_val)  # Session thường chỉ áp dụng chung
            end_dt = datetime.combine(d2, datetime.min.time()).replace(hour=h2, minute=m2)

        # TH2: 2 giờ 1 Ngày (VD 14h -> 16h30 ngày mai)
        elif len(raw_times) >= 2 and len(raw_dates) <= 1:
            target_date = self.parser.parse_relative_date(date0)
            # Start
            h1, m1 = self.parser.parse_time(raw_times[0], session_val)
            start_dt = datetime.combine(target_date, datetime.min.time()).replace(hour=h1, minute=m1)
            # End
            h2, m2 = self.parser.parse_time(raw_times[1], session_val)
            end_dt = datetime.combine(target_date, datetime.min.time()).replace(hour=h2, minute=m2)

            # Nếu End < Start (VD 22h đêm đến 2h sáng), end +1 ngày
            if end_dt < start_dt:
                end_dt += timedelta(days=1)

        # TH3: không có endtime
        else:
            target_date = self.parser.parse_relative_date(date0)
            h1, m1 = self.parser.parse_time(time0, session_val)
            start_dt = datetime.combine(target_date, datetime.min.time()).replace(hour=h1, minute=m1)

        # ---------------------------------------------------------
        # OUTPUT
        # ---------------------------------------------------------
        remove_list = clean_locs + raw_times + raw_dates + ([remind_str] if remind_str else [])
        if session_val: remove_list.append(session_val)
        event_name = self.extract_event_name(text, remove_list)
        normalizer = TimeRangeNormalizer()  # xử lý lỗi thgian
        start_dt, end_dt = normalizer.fix_range(start_dt, end_dt)
        return {
            "event": event_name,
            "start_time": start_dt.strftime('%Y-%m-%d %H:%M:%S'),
            "end_time": end_dt.strftime('%Y-%m-%d %H:%M:%S') if end_dt else None,
            "location": final_loc,
            "reminder_minutes": reminder_min
        }

