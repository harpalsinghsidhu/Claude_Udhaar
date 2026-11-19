import sqlite3
from datetime import datetime

from kivy.app import App
from kivy.core.window import Window 
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button 
from kivy.uix.label import Label 
from kivy.uix.popup import Popup 
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput

# keeps the keyboard from covering the input boxes on phones
Window.softinput_mode = 'below_target'

KV = """
ScreenManager:
    HomeScreen:
    DetailScreen:
    
<HomeScreen>:
    name: 'home'
    BoxLayout:
        orientation: 'vertical'
        padding: 10
        spacing: 8
        Label:
            id: total
            font_size: '22sp'
            size_hint_y: None
            height: '50dp'
        TextInput:
            id: search
            hint_text: 'Search customer'
            multiline: False
            size_hint_y: None
            height: '44dp'
            on_text: root.refresh()
        ScrollView:
            GridLayout:
                id: box
                cols: 1
                spacing: 6
                size_hint_y: None
                height: self.minimum_height
        Button:
            text: '+ Add customer'
            size_hint_y: None
            height: '52dp'
            on_release: root.add_customer()
            
<DetailScreen>:
    name: 'detail'
    BoxLayout:
        orientation: 'vertical'
        padding: 10
        spacing: 8
        Label:
            id: title
            font_size: '22sp'
            size_hint_y: None
            height: '60dp'
            halign: 'center'
        BoxLayout:
            size_hint_y: None
            height: '52dp'
            spacing: 8
            Button:
                text: 'Gave udhaar'
                on_release: root.add_txn('credit')
            Button:
                text: 'Got payment'
                on_release: root.add_txn('payment')
        ScrollView:
            GridLayout:
                id: box
                cols: 1
                spacing: 4
                size_hint_y: None
                height: self.minimum_height
        Button:
            text: 'Back'
            size_hint_y: None
            height: '48dp'
            on_release: app.root.current = 'home'
"""


def db():
    return App.get_running_app().conn
    
    
def popup(title, fields, on_ok):
    """fields: list of (hint, numeric?) -> on_ok(list_of_texts)"""
    box = BoxLayout(orientation='vertical', spacing=8, padding=8)
    inputs = []
    for hint, numeric in fields:
        t = TextInput(hint_text=hint, multiline=False)
        if numeric:
            t.input_filter = 'float'
        inputs.append(t)
        box.add_widget(t)
    row = BoxLayout(size_hint_y=None, height=48, spacing=8)
    ok, cancel = Button(text='Save'), Button(text='Cancel')
    row.add_widget(ok)
    row.add_widget(cancel)
    box.add_widget(row)
    pop = Popup(title=title, content=box, size_hint=(.9, .5))
    
    def save(*_):
        if on_ok([t.text.strip() for t in inputs]) is not False:
            pop.dismiss()
            
    ok.bind(on_release=save)
    cancel.bind(on_release=pop.dismiss)
    pop.open()
    

class HomeScreen(Screen):
    def on_enter(self):
        self.refresh()
        
    def refresh(self):
        rows = db().execute("""
            SELECT c.id, c.name, c.phone,
              COALESCE(SUM(CASE t.kind WHEN 'credit' THEN t.amount
                                       WHEN 'payment' THEN -t.amount END), 0) AS bal
            FROM customers c LEFT JOIN txns t ON t.customer_id = c.id
            GROUP BY c.id ORDER BY bal DESC, c.name""").fetchall()
        q = self.ids.search.text.strip().lower()
        self.ids.total.text = 'Total pending: Rs %.0f' % sum(r[3] for r in rows)
        self.ids.box.clear_widgets()
        for cid, name, phone, bal in rows:
            if q and q not in name.lower():
                continue
            b = Button(text='%s      Rs %.0f' % (name, bal),
                       size_hint_y=None, height='56dp')
            b.bind(on_release=lambda _b, cid=cid: self.open_customer(cid))
            self.ids.box.add_widget(b)
            
    def open_customer(self, cid):
        d = self.manager.get_screen('detail')
        d.cid = cid
        self.manager.current = 'detail'
        
    def add_customer(self):
        def ok(v):
            name, phone = v
            if not name:
                return False
            db().execute("INSERT INTO customers(name, phone) VALUES (?,?)",
                          (name, phone))
            db().commit()
            self.refresh()
        popup('New customer', [('Name', False), ('Phone (optional)', False)], ok)


class DetailScreen(Screen):
    cid = None
    
    def on_enter(self):
        self.refresh()
        
    def refresh(self):
        name, phone = db().execute(
            "SELECT name, phone FROM customers WHERE id=?", (self.cid,)).fetchone()
        txns = db().execute(
            "SELECT amount, kind, note, date FROM txns "
            "WHERE customer_id=? ORDER BY id DESC", (self.cid,)).fetchall()
        bal = sum(a if k == 'credit' else -a for a, k, _, _ in txns)
        self.ids.title.text = '%s %s\nOwes: Rs %.0f' % (name, phone, bal)
        self.ids.box.clear_widgets()
        for amt, kind, note, date in txns:
            sign, word = ('+', 'Udhaar') if kind == 'credit' else ('-', 'Paid')
            self.ids.box.add_widget(Label(
                text='%s   %s %s%.0f   %s' % (date, word, sign, amt, note),
                size_hint_y=None, height='36dp'))
                
    def add_txn(self, kind):
        def ok(v):
            try:
                amt = float(v[0])
            except ValueError:
                return False
            if amt <= 0:
                return False
            db().execute(
                "INSERT INTO txns(customer_id, amount, kind, note, date) "
                "VALUES (?,?,?,?,?)",
                (self.cid, amt, kind, v[1], datetime.now().strftime('%d-%b')))
            db().commit()
            self.refresh()
        title = 'Gave udhaar' if kind == 'credit' else 'Got payment'
        popup(title, [('Amount', True), ('Note (optional)', False)], ok)
        
        
class UdhaarApp(App):
    def build(self):
        self.conn = sqlite3.connect(self.user_data_dir + '/udhaar.db')
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS customers(
                id INTEGER PRIMARY KEY, name TEXT, phone TEXT);
            CREATE TABLE IF NOT EXISTS txns(
                id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL,
                kind TEXT, note TEXT, date TEXT);""")
        return Builder.load_string(KV)
        
        
UdhaarApp().run()
    
