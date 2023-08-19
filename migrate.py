import sqlite3          
con = sqlite3.connect("chatbot.db")     
cur = con.cursor()

chat_history = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    password TEXT
);
"""
res = cur.execute(chat_history)
res.fetchone()

chat_history = """
CREATE TABLE chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key INTEGER,
    folderid TEXT,
    message TEXT,
    FOREIGN KEY (user_key) REFERENCES users(id)
);
"""
res = cur.execute(chat_history)
res.fetchone()


chats = """
CREATE TABLE chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT,
    bot TEXT,
    chat_id INTEGER,
    FOREIGN KEY (chat_id) REFERENCES chat_history(id)
);
"""

res = cur.execute(chats)
res.fetchone()
