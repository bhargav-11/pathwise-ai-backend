from flask import Flask, request, jsonify,redirect,render_template
from flask_admin.menu import MenuLink
from flask_cors import CORS
import os
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chat_models import ChatOpenAI
from langchain.document_loaders import PyPDFLoader
from langchain.prompts.prompt import PromptTemplate
import logging
from dotenv import load_dotenv
import sqlite3
from langchain.document_loaders import GoogleDriveLoader
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
import PyPDF2
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.errors import HttpError
from langchain.chains import RetrievalQA
import os
from flask_admin import Admin,AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)  # Set the desired logging level

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler = logging.FileHandler('chatbot.log', mode='w')  # Specify the log file name and mode
handler.setFormatter(formatter)

logger.addHandler(handler)
app = Flask(__name__)
flask_db = SQLAlchemy()
app.secret_key= "512204f79fd3812be92b17c211b06d82"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chatbot.db'
class users(flask_db.Model,UserMixin):
    id = flask_db.Column(flask_db.Integer, primary_key=True)
    name = flask_db.Column(flask_db.String(80), unique=True)
    password = flask_db.Column(flask_db.String(120))
    is_admin = flask_db.Column(flask_db.Boolean, default=False)

with app.app_context():
    flask_db.init_app(app)
    flask_db.create_all()  

def create_first_admin_user():
    if not users.query.filter_by(is_admin=True).first():
        new_user = users(name=os.getenv('username'), password=os.getenv('password'), is_admin=True)
        flask_db.session.add(new_user)
        flask_db.session.commit()

@app.before_request
def before_request():
    create_first_admin_user()

login_manager = LoginManager(app)
login_manager.init_app(app)
@login_manager.user_loader
def load_user(id):
    return users.query.get(int(id))

CORS(app)

def load_documents(folder_id):
    loader = GoogleDriveLoader(
        credentials_path=".credentials/credentials.json",
        token_path=".credentials/token.json",
        folder_id=folder_id,
        recursive=False,
        file_types=["document", "pdf"],
    )
    try:
        loader_docs = loader.load()
    except HttpError as e:
        error_message = e.content.decode("utf-8")
        if "File not found" in error_message:
            # Handle the specific exception
            print("Provided folder not found")
            exit()
        else:
            # Handle other HttpError exceptions
            print("An HttpError occurred:", error_message)
            exit()

    return loader_docs

def split_documents(docs):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=50, separators=[" ", ",", "\n"])
    return text_splitter.split_documents(docs)

def generate_embeddings():
    return OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

def create_chroma_db_without_embeddings(embeddings, folder_id):
    return Chroma(embedding_function=embeddings, persist_directory="./embeddings/{}-embeds".format(folder_id))

def create_chroma_db(texts, embeddings, folder_id, reembed_flag_bool):
    if not os.path.exists("./embeddings/{}-embeds".format(folder_id)) or reembed_flag_bool:
        print("Creating embeddings for folder id {}".format(folder_id))
        vector_db = Chroma.from_documents(texts, embeddings, persist_directory="./embeddings/{}-embeds".format(folder_id))
        vector_db.persist()
        return vector_db
    else:
        return create_chroma_db_without_embeddings(embeddings, folder_id)

def create_index(llm, db):
    return RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=db.as_retriever(search_kwargs={"k": 3}), return_source_documents=True)

def create_llm(temperature):
    return ChatOpenAI(model_name="gpt-4-0613", openai_api_key=OPENAI_API_KEY, temperature=temperature)



@app.route('/chat', methods=['POST'])
def chat():

    try:
        con = sqlite3.connect("instance/chatbot.db")
        cur = con.cursor()

        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        question = data.get('question', '')
        chat_history_id = data.get('chat_id')
        folder_id = data.get('folder_id')
        user_id = data.get('user_id')
        temperature = data.get('temperature')
        retrain = data.get('retrain', False)
        
        if not question or not folder_id or not user_id:
            return jsonify({'error': 'Question, folder_id and user_id must to be provided'}), 400

        start_new_chat = data.get('start_new_chat', False)
        
        if start_new_chat:
            insert_new_chat = """
            INSERT INTO chat_history (user_key, folderid, message) VALUES (?, ?, ?);
            """

            res = cur.execute(insert_new_chat, (user_id, folder_id, question))
            chat_history_id = cur.lastrowid
            print("chat id", chat_history_id)
            
            docs = load_documents(folder_id)
            texts = split_documents(docs)
            embeddings = generate_embeddings()
            db = create_chroma_db(texts, embeddings, folder_id, retrain)
        else:
            embeddings = generate_embeddings()
            db = create_chroma_db_without_embeddings(embeddings, folder_id)

        llm = create_llm(temperature)
        qa = create_index(llm, db)

        answer = qa({"query": question})

        answer_with_sources = "Answer: {}\n".format(answer['result'])
        for doc in answer.get("source_documents", []):
            answer_with_sources = answer_with_sources + "\nSource: {}{}".format(doc.metadata.get("title", ''),
            "  Page: {}".format(doc.metadata.get("page", '')) if doc.metadata.get("page") else '')

        chat_answer_query = "INSERT INTO chats (user, bot, chat_id) VALUES (?, ?, ?);"

        print(chat_history_id)
        res = cur.execute(chat_answer_query, (question, answer_with_sources, chat_history_id))
        print(res.lastrowid)
        con.commit()
        
        cur.close()
        con.close()

        return jsonify({'response': answer_with_sources, 'chat_id':chat_history_id}), 200
    except Exception as e:
        if start_new_chat:
            delete_created_chat = """
            DELETE FROM chat_history WHERE id = (?);
            """

            res = cur.execute(delete_created_chat, (chat_history_id,))
            con.commit()

            cur.close()
            con.close()
        logger.error(str(e))
        return jsonify({'response': 'Error occured while fetching response. Error: {}'.format(str(e))}), 500

@app.route('/retrain', methods=['POST'])
def retrain():

    try:
        con = sqlite3.connect("chatbot.db")
        cur = con.cursor()

        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        folder_id = data.get('folder_id')
        
        docs = load_documents(folder_id)
        texts = split_documents(docs)
        embeddings = generate_embeddings()
        db = create_chroma_db(texts, embeddings, folder_id, True)

        if db:
            response = "Folder re-trained successfully"
        else:
            response = "Folder re-training failed"

        return jsonify({'response': response}), 200
    except Exception as e:
        logger.error(str(e))
        return jsonify({'response': 'Error occured while fetching response. Error: {}'.format(str(e))}), 500

# Endpoint to get all chat entries for a specific chat ID and user ID
@app.route('/get_chats/<int:chat_id>', methods=['GET'])
def get_chats(chat_id):
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect('instance/chatbot.db')
        cursor = conn.cursor()

        # Fetch chat entries for the specified chat ID and user ID
        cursor.execute("SELECT user, bot FROM chats WHERE chat_id = ? ORDER BY id ASC", (chat_id,))
        chats = cursor.fetchall()

        # Close the database connection
        conn.close()

        # Convert chat data into a list of dictionaries
        chat_list = [{'user': entry[0], 'bot': entry[1]} for entry in chats]

        return jsonify(chat_list)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint to get chat history for a specific user
@app.route('/get_all_chat_history/<int:user_id>', methods=['GET'])
def get_all_chat_history(user_id):
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect('instance/chatbot.db')
        cursor = conn.cursor()

        # Fetch chat history for the specified user
        cursor.execute("SELECT id, folderid, message FROM chat_history WHERE user_key = ?", (user_id,))
        chat_history = cursor.fetchall()

        # Close the database connection
        conn.close()

        # Convert chat history data into a list of dictionaries
        chat_history_list = [{'id': entry[0], 'folderid': entry[1], 'message': entry[2]} for entry in chat_history]

        return jsonify(chat_history_list)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint to create a new user
@app.route('/create_user', methods=['POST'])
def create_user():
    try:
        # Get user data from the request
        user_data = request.get_json()
        name = user_data['name']
        password = user_data['password']

        # Connect to the SQLite database
        conn = sqlite3.connect('instance/chatbot.db')
        cursor = conn.cursor()

        # Insert the new user into the database
        cursor.execute("INSERT INTO users (name, password) VALUES (?, ?)", (name, password))
        conn.commit()

        # Close the database connection
        conn.close()

        return jsonify({'message': 'User created successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint to delete a user
@app.route('/delete_user/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect('instance/chatbot.db')
        cursor = conn.cursor()

        # Delete the user
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()

        # Close the database connection
        conn.close()

        return jsonify({'message': 'User deleted successfully'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint to get all users
@app.route('/get_users', methods=['GET'])
def get_users():
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect('instance/chatbot.db')
        cursor = conn.cursor()

        # Fetch all users from the database
        cursor.execute("SELECT id, name, password FROM users")
        users = cursor.fetchall()

        # Close the database connection
        conn.close()

        # Convert users data into a list of dictionaries
        users_list = [{'id': user[0], 'name': user[1], 'password': user[2]} for user in users]

        return jsonify(users_list), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin_user = users.query.filter_by(name=username).first()
        if admin_user and admin_user.password == password:
            login_user(admin_user)
            return redirect("/admin")
        
        print("PRINT USER :", username)
        user = users.query.filter_by(name=username).first()
        print("PRINT USER :", user)

        if user and user.password == password:
            login_user(user)
            return redirect("/admin")
        
    return render_template('login.html') 



class DashboardView(AdminIndexView):

    def is_visible(self):
        
        return False

class UserAdmin(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

class LoginMenuLink(MenuLink):

    def is_accessible(self):
        return not current_user.is_authenticated 


class LogoutMenuLink(MenuLink):

    def is_accessible(self):
        return current_user.is_authenticated  
class Mymodelview(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated   
 
admin = Admin(app, name='Admin Panel', template_mode='bootstrap3',index_view=DashboardView())
admin.add_view(Mymodelview(users, flask_db.session))


admin.add_link(LogoutMenuLink(name='Logout', category='', url="/logout"))
admin.add_link(LoginMenuLink(name='Login', category='', url="/login"))

@app.route('/logout')
def logout():
    logout_user()
    return redirect("/login")

@app.route('/user_login', methods=['GET', 'POST'])
def user_login():
    import json
    if request.method == 'POST':
        data = json.loads(request.data.decode('utf-8'))
        print("UVJJHHJ :", data)

        username = data.get('username')
        password = data.get('password')
        user = users.query.filter_by(name=username).first()
        if user and user.password == password:
                if user.is_admin == 0:
                    return jsonify({"message": "user login"}), 200
                
    return jsonify({"message": "Bad request"}), 400
if __name__ == '__main__':
    app.run(debug=True)
   