import sqlite3  
import os
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy


from sqlalchemy import event        
con = sqlite3.connect("instance/chatbot.db")     
cur = con.cursor()
flask_db = SQLAlchemy()

class users(flask_db.Model,UserMixin):
    id = flask_db.Column(flask_db.Integer, primary_key=True)
    name = flask_db.Column(flask_db.String(80), unique=True)
    password = flask_db.Column(flask_db.String(120))
    is_admin = flask_db.Column(flask_db.Boolean, default=False)


# # chat_history = """
# # CREATE TABLE users (
# #     id INTEGER PRIMARY KEY AUTOINCREMENT,
# #     name TEXT,
# #     password TEXT
# # );
# # """
# # res = cur.execute(chat_history)
# # res.fetchone()

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
