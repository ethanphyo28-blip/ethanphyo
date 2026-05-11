import os
import sqlite3
import requests
from datetime import datetime
from io import BytesIO

# Kivy Config must be set before other Kivy imports
from kivy.config import Config
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')
Config.set('graphics', 'width', '400')
Config.set('graphics', 'height', '700')

from kivy.lang import Builder
from kivy.uix.image import Image
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.utils import platform

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.datatables import MDDataTable
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDRaisedButton, MDFlatButton
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.pickers import MDDatePicker

# Optional imports with graceful failure
try:
    import cv2
except ImportError:
    cv2 = None

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

# ================= DATABASE LOGIC =================
if platform == 'android':
    try:
        from android.storage import app_storage_path
        db_path = os.path.join(app_storage_path(), 'finance.db')
    except ImportError:
        db_path = 'finance.db'
else:
    db_path = 'finance.db'

def init_all_db():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS history
                          (id INTEGER PRIMARY KEY, type TEXT, category TEXT, amount REAL, date TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS trading_journal
                          (id INTEGER PRIMARY KEY, pair TEXT, action TEXT, profit REAL, date TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database Init Error: {e}")

def add_entry(type, category, amount, entry_date):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (type, category, amount, date) VALUES (?, ?, ?, ?)",
                   (type, category, amount, entry_date))
    conn.commit()
    conn.close()

def add_trade_entry(pair, action, profit, date):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO trading_journal (pair, action, profit, date) VALUES (?, ?, ?, ?)",
                   (pair, action, profit, date))
    conn.commit()
    conn.close()

# ================= SCREENS =================

class InputScreen(MDScreen):
    selected_category = "Other"
    selected_date = datetime.now().strftime("%Y-%m-%d")
    menu = None

    def on_enter(self):
        # Initialize menu only once and when screen is entered to ensure IDs are ready
        if not self.menu:
            menu_items = [
                {
                    "viewclass": "OneLineListItem",
                    "text": i,
                    "on_release": lambda x=i: self.set_item(x),
                } for i in ["Food", "Transport", "Meter Bill", "Water Bill", "Phone Bill", "Market", "Shopping", "Other"]
            ]
            self.menu = MDDropdownMenu(
                caller=self.ids.drop_item,
                items=menu_items,
                width_mult=4,
            )

    def set_item(self, text_item):
        self.selected_category = text_item
        self.ids.drop_item.text = text_item
        self.menu.dismiss()

    def show_date_picker(self):
        try:
            date_dialog = MDDatePicker()
            date_dialog.bind(on_save=self.on_date_save, on_cancel=lambda x: date_dialog.dismiss())
            date_dialog.open()
        except Exception as e:
            print(f"DatePicker Error: {e}")

    def on_date_save(self, instance, value, date_range):
        self.selected_date = value.strftime("%Y-%m-%d")
        self.ids.date_btn.text = f"Date: {self.selected_date}"
        instance.dismiss()

    def save_data(self, entry_type):
        amount = self.ids.amount_field.text
        if amount:
            try:
                add_entry(entry_type, self.selected_category, float(amount), self.selected_date)
                self.ids.amount_field.text = ""
                self.ids.date_btn.text = "Select Date"
                self.ids.drop_item.text = "Select Category"
                self.selected_date = datetime.now().strftime("%Y-%m-%d")
            except ValueError:
                pass

class HistoryScreen(MDScreen):
    def on_enter(self):
        self.apply_filter()

    def apply_filter(self):
        date_search = self.ids.filter_date.text.strip()
        cat_search = self.ids.filter_cat.text.strip()
        query = "SELECT * FROM history WHERE 1=1"
        params = []
        if date_search:
            query += " AND date LIKE ?"
            params.append(f"%{date_search}%")
        if cat_search:
            query += " AND category LIKE ?"
            params.append(f"%{cat_search}%")
        query += " ORDER BY id DESC"
        self.load_table(query, tuple(params))

    def load_table(self, query, params):
        self.ids.table_layout.clear_widgets()
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(query, params)
            data = cursor.fetchall()
            conn.close()

            row_data = [[str(i[0]), i[1], i[2], f"{i[3]:,.0f}", str(i[4]), "DELETE"] for i in data]
            
            self.table = MDDataTable(
                use_pagination=True,
                rows_num=10,
                column_data=[
                    ("ID", dp(15)), ("Type", dp(20)), ("Cat", dp(25)),
                    ("Amt", dp(25)), ("Date", dp(35)), ("Action", dp(20)),
                ],
                row_data=row_data
            )
            self.table.bind(on_row_press=self.on_row_press)
            self.ids.table_layout.add_widget(self.table)
        except Exception as e:
            print(f"Table Load Error: {e}")

    def on_row_press(self, instance_table, instance_row):
        row_index = int(instance_row.index / len(instance_table.column_data))
        real_id = instance_table.row_data[row_index][0]
        Clock.schedule_once(lambda dt: self.show_delete_dialog(real_id), 0.1)

    def show_delete_dialog(self, row_id):
        self.dialog = MDDialog(
            title="Confirm Delete",
            text=f"ID: {row_id} ကို ဖျက်မှာ သေချာပါသလား?",
            buttons=[
                MDFlatButton(text="CANCEL", on_release=lambda x: self.dialog.dismiss()),
                MDRaisedButton(text="DELETE", md_bg_color=(1, 0, 0, 1),
                               on_release=lambda x: self.delete_entry(row_id)),
            ],
        )
        self.dialog.open()

    def delete_entry(self, row_id):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE id=?", (row_id,))
        conn.commit()
        conn.close()
        self.dialog.dismiss()
        self.apply_filter()

class ChartScreen(MDScreen):
    def on_enter(self):
        Clock.schedule_once(lambda dt: self.generate_charts(), 0.2)

    def generate_charts(self):
        if plt is None:
            return
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT type, SUM(amount) FROM history GROUP BY type")
            summary_data = dict(cursor.fetchall())
            cursor.execute("SELECT category, SUM(amount) FROM history WHERE type='Expense' GROUP BY category")
            category_data = cursor.fetchall()
            conn.close()

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 10))
            plt.subplots_adjust(hspace=0.4)

            types = ['Income', 'Expense']
            amounts = [summary_data.get('Income', 0), summary_data.get('Expense', 0)]
            ax1.bar(types, amounts, color=['#2ecc71', '#e74c3c'])
            ax1.set_title("Total Summary (MMK)")

            if category_data:
                labels = [c[0] for c in category_data]
                values = [c[1] for c in category_data]
                ax2.pie(values, labels=labels, autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired.colors)
                ax2.set_title("Expense by Category")
            else:
                ax2.text(0.5, 0.5, 'No Expense Data', ha='center')

            buf = BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)

            self.ids.chart_box.clear_widgets()
            core_img = CoreImage(buf, ext='png')
            img_widget = Image(texture=core_img.texture, allow_stretch=True, keep_ratio=True)
            self.ids.chart_box.add_widget(img_widget)
            plt.close(fig)
        except Exception as e:
            print(f"Chart Error: {e}")

class ScanScreen(MDScreen):
    cap = None

    def capture_and_scan(self):
        if cv2 is None:
            self.ids.detected_label.text = "Status: OpenCV not found!"
            return
        
        try:
            if self.cap is None:
                self.cap = cv2.VideoCapture(0)
            
            if not self.cap.isOpened():
                self.ids.detected_label.text = "Status: Camera Error!"
                self.cap = None
                return
            
            ret, frame = self.cap.read()
            if ret:
                self.ids.detected_label.text = "Status: Captured!"
                # Logic for processing frame would go here
            else:
                self.ids.detected_label.text = "Status: Capture Failed!"
        except Exception as e:
            self.ids.detected_label.text = f"Error: {str(e)}"

    def on_leave(self):
        if self.cap:
            self.cap.release()
            self.cap = None

class ForexScreen(MDScreen):
    def get_exchange_rates(self):
        self.ids.status_label.text = "Fetching..."
        Clock.schedule_once(self._fetch_rates, 0.1)

    def _fetch_rates(self, dt):
        try:
            response = requests.get("https://open.er-api.com/v6/latest/USD", timeout=15)
            data = response.json()
            if data.get("result") == "success":
                rates = data.get("rates", {})
                self.ids.xau_usd.text = f"GOLD = {1/rates['XAU']:,.2f} USD/oz" if 'XAU' in rates else "N/A"
                self.ids.usd_mmk.text = f"1 USD = {rates.get('MMK', 0):,.2f} MMK"
                self.ids.usd_thb.text = f"1 USD = {rates.get('THB', 0):,.2f} THB"
                self.ids.usd_sgd.text = f"1 USD = {rates.get('SGD', 0):,.2f} SGD"
                self.ids.usd_eur.text = f"1 USD = {rates.get('EUR', 0):,.2f} EUR"
                self.ids.status_label.text = "Update Success!"
            else:
                self.ids.status_label.text = "API Error"
        except Exception:
            self.ids.status_label.text = "Connection Error!"

class TradingJournal(MDScreen):
    selected_date = datetime.now().strftime("%Y-%m-%d")

    def on_enter(self):
        self.load_trading_table()

    def show_date_picker(self):
        date_dialog = MDDatePicker()
        date_dialog.bind(on_save=self.on_date_save, on_cancel=lambda x: date_dialog.dismiss())
        date_dialog.open()

    def on_date_save(self, instance, value, date_range):
        self.selected_date = value.strftime("%Y-%m-%d")
        self.ids.date_btn.text = f"Date: {self.selected_date}"
        instance.dismiss()

    def save_trade_data(self, pair, amount):
        if pair and amount:
            try:
                amt = float(amount)
                action = "BUY" if amt > 0 else "SELL"
                add_trade_entry(pair.upper(), action, amt, self.selected_date)
                self.ids.pair.text = ""
                self.ids.amount.text = ""
                self.ids.date_btn.text = "Select Date"
                self.selected_date = datetime.now().strftime("%Y-%m-%d")
                self.load_trading_table()
            except ValueError:
                pass

    def load_trading_table(self):
        self.ids.trading_table_layout.clear_widgets()
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trading_journal ORDER BY id DESC")
            data = cursor.fetchall()
            conn.close()

            row_data = [[str(i[0]), i[1], f"{i[3]:,.2f}", i[4]] for i in data]
            self.table = MDDataTable(
                use_pagination=True,
                rows_num=10,
                column_data=[
                    ("ID", dp(30)), ("Pair", dp(80)),
                    ("Profit/Loss", dp(80)), ("Date", dp(100)),
                ],
                row_data=row_data
            )
            self.ids.trading_table_layout.add_widget(self.table)
        except Exception as e:
            print(f"Trade Table Error: {e}")

# ================= APP MAIN =================
class FinanceApp(MDApp):
    def build(self):
        init_all_db()
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.theme_style = "Dark"
        # Use a safe way to load KV
        try:
            return Builder.load_string(KV)
        except Exception as e:
            print(f"KV Load Error: {e}")
            return MDScreen()

KV = '''
MDBoxLayout:
    orientation: 'vertical'
    MDTopAppBar:
        title: "SMART FINANCE PRO"
        elevation: 4
        md_bg_color: 0.1, 0.1, 0.2, 1

    MDScreenManager:
        id: screen_manager
        InputScreen:
            name: "input_screen"
        HistoryScreen:
            name: "history_screen"
        ChartScreen:
            name: "chart_screen"
        ScanScreen:
            name: "scan_screen"
        ForexScreen:
            name: "forex_screen"
        TradingJournal:
            name: "journal_screen"

    MDBottomNavigation:
        panel_color: 0.1, 0.1, 0.15, 1
        MDBottomNavigationItem:
            name: 'add'
            text: 'Add'
            icon: 'plus'
            on_tab_press: screen_manager.current = "input_screen"
        MDBottomNavigationItem:
            name: 'history'
            text: 'History'
            icon: 'table'
            on_tab_press: screen_manager.current = "history_screen"
        MDBottomNavigationItem:
            name: 'chart'
            text: 'Chart'
            icon: 'chart-bar'
            on_tab_press: screen_manager.current = "chart_screen"
        MDBottomNavigationItem:
            name: 'scan'
            text: 'Scan'
            icon: 'camera'
            on_tab_press: screen_manager.current = "scan_screen"
        MDBottomNavigationItem:
            name: 'forex'
            text: 'Forex'
            icon: 'currency-usd'
            on_tab_press: screen_manager.current = "forex_screen"
        MDBottomNavigationItem:
            name: 'journal'
            text: 'Trade'
            icon: 'chart-line'
            on_tab_press: screen_manager.current = "journal_screen"

<InputScreen>:
    MDBoxLayout:
        orientation: 'vertical'
        padding: [dp(20), dp(30), dp(20), dp(20)]
        spacing: dp(15)
        MDLabel:
            text: "Finance Entry"
            font_style: "H5"
            halign: "center"
            size_hint_y: None
            height: dp(40)
        MDTextField:
            id: amount_field
            hint_text: "Enter Amount (MMK)"
            mode: "rectangle"
            input_filter: "float"
        MDRaisedButton:
            id: date_btn
            text: "Select Date"
            pos_hint: {"center_x": .5}
            size_hint_x: 0.8
            on_release: root.show_date_picker()
        MDRectangleFlatIconButton:
            id: drop_item
            text: "Select Category"
            icon: "chevron-down"
            pos_hint: {"center_x": .5}
            size_hint_x: 0.8
            on_release: root.menu.open()
        MDBoxLayout:
            spacing: dp(15)
            size_hint_y: None
            height: dp(50)
            MDFillRoundFlatButton:
                text: "SAVE INCOME"
                md_bg_color: 0.1, 0.7, 0.3, 1
                size_hint_x: 0.5
                on_release: root.save_data("Income")
            MDFillRoundFlatButton:
                text: "SAVE EXPENSE"
                md_bg_color: 0.8, 0.2, 0.2, 1
                size_hint_x: 0.5
                on_release: root.save_data("Expense")
        Widget:

<HistoryScreen>:
    MDBoxLayout:
        orientation: 'vertical'
        MDBoxLayout:
            size_hint_y: None
            height: dp(70)
            padding: dp(10)
            spacing: dp(10)
            MDTextField:
                id: filter_date
                hint_text: "Date (2026-05)"
                mode: "line"
                on_text_validate: root.apply_filter()
            MDTextField:
                id: filter_cat
                hint_text: "Category"
                mode: "line"
                on_text_validate: root.apply_filter()
            MDIconButton:
                icon: "magnify"
                on_release: root.apply_filter()
        MDBoxLayout:
            id: table_layout
            orientation: 'vertical'
            size_hint_y: 1
            padding: dp(5)

<ChartScreen>:
    MDBoxLayout:
        id: chart_box
        orientation: 'vertical'
        padding: dp(10)

<ScanScreen>:
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(20)
        MDLabel:
            id: detected_label
            text: "Ready to Scan"
            halign: "center"
            size_hint_y: None
            height: dp(50)
        MDIconButton:
            icon: "camera"
            icon_size: dp(64)
            pos_hint: {"center_x": .5}
            on_release: root.capture_and_scan()
        Widget:

<ForexScreen>:
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(15)
        MDLabel:
            id: xau_usd
            text: "GOLD = ? USD"
            font_style: "H5"
            halign: "center"
            theme_text_color: "Custom"
            text_color: 1, 0.84, 0, 1
        MDLabel:
            id: usd_mmk
            text: "1 USD = ? MMK"
            font_style: "H5"
            halign: "center"
        MDLabel:
            id: usd_thb
            text: "1 USD = ? THB"
            font_style: "H5"
            halign: "center"
        MDLabel:
            id: usd_sgd
            text: "1 USD = ? SGD"
            font_style: "H5"
            halign: "center"
        MDLabel:
            id: usd_eur
            text: "1 USD = ? EUR"
            font_style: "H5"
            halign: "center"        
        MDRaisedButton:
            text: "GET RATES"
            pos_hint: {"center_x": .5}
            on_release: root.get_exchange_rates()
        MDLabel:
            id: status_label
            text: ""
            halign: "center"
            theme_text_color: "Hint"
        Widget:

<TradingJournal>:
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(10)
        spacing: dp(10)
        md_bg_color: 0.05, 0.05, 0.1, 1
        MDBoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: self.minimum_height
            spacing: dp(10)
            MDLabel:
                text: "TRADING JOURNAL"
                halign: "center"
                font_style: "H6"
                size_hint_y: None
                height: dp(40)
                theme_text_color: "Custom"
                text_color: 1, 1, 1, 1
            MDBoxLayout:
                size_hint_y: None
                height: dp(65)
                spacing: dp(10)
                MDTextField:
                    id: pair
                    hint_text: "Pair (XAUUSD)"
                    mode: "rectangle"
                MDTextField:
                    id: amount
                    hint_text: "Profit/Loss (+/-)"
                    mode: "rectangle"
                    input_filter: "float"
            MDRaisedButton:
                id: date_btn
                text: "Select Date"
                pos_hint: {"center_x": .5}
                size_hint_x: 0.8
                on_release: root.show_date_picker()
            MDRaisedButton:
                text: "SAVE TRADE RECORD"
                pos_hint: {"center_x": .5}
                size_hint_x: 0.8
                on_release: root.save_trade_data(pair.text, amount.text)
        MDBoxLayout:
            id: trading_table_layout
            orientation: 'vertical'
            size_hint_y: 1
'''

if __name__ == "__main__":
    try:
        FinanceApp().run()
    except Exception as e:
        print(f"App Runtime Error: {e}")
