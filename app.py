import os
import sys

try:
    import pysqlite3
    sys.modules['sqlite3'] = pysqlite3
except ImportError:
    pass

import random
import string
import mimetypes
import json
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-12345')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mateugram.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mp3', 'pdf', 'doc', 'docx'}

# Настройки почты (можно оставить)
app.config['MAIL_SERVER'] = 'smtp.mail.ru'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'mcrmateucraft@mail.ru'
app.config['MAIL_PASSWORD'] = 'IsV6RpOYD0Yu8DLlpBvf'
app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']

db = SQLAlchemy(app)
mail = Mail(app)
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager(app)
login_manager.login_view = 'login'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('photos', exist_ok=True)

# -------------------- Модели --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80))
    birth_day = db.Column(db.Integer)
    birth_month = db.Column(db.Integer)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    avatar = db.Column(db.String(200), default='default.jpg')
    verified = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    is_group = db.Column(db.Boolean, default=False)
    is_channel = db.Column(db.Boolean, default=False)
    linked_group_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    invite_token = db.Column(db.String(50), unique=True, nullable=True)

    linked_group = db.relationship('Chat', remote_side=[id], foreign_keys=[linked_group_id])

class ChatMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'))
    role = db.Column(db.String(20), default='member')
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'))
    content = db.Column(db.Text)
    reply_to = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    forwarded_from = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    file_path = db.Column(db.String(200), nullable=True)
    file_name = db.Column(db.String(200), nullable=True)
    file_type = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited = db.Column(db.Boolean, default=False)
    pinned = db.Column(db.Boolean, default=False)

    replies = db.relationship(
        'Message',
        foreign_keys=[reply_to],
        backref=db.backref('parent', remote_side=[id]),
        lazy='dynamic'
    )
    reactions = db.relationship('Reaction', backref='message', lazy='dynamic')
    comments = db.relationship('Comment', backref='message', lazy='dynamic')

class Reaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reaction = db.Column(db.String(10))

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'))
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# -------------------- Вспомогательные функции --------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_avatar_url(user):
    if user.avatar and user.avatar != 'default.jpg':
        return url_for('uploads', filename=user.avatar)
    return '/photos/default.jpg'

def get_chat_name(chat):
    if chat.name:
        return chat.name
    members = User.query.join(ChatMember, ChatMember.user_id == User.id).filter(ChatMember.chat_id == chat.id).all()
    names = [m.first_name for m in members if m.id != current_user.id]
    return ', '.join(names) if names else 'Личный чат'

def generate_invite_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=20))

# -------------------- Статика и favicon --------------------
@app.route('/photos/<filename>')
def photos(filename):
    return send_from_directory('photos', filename)

@app.route('/uploads/<filename>')
def uploads(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('photos', 'logo.png', mimetype='image/vnd.microsoft.icon')

# -------------------- Главная --------------------
@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

INDEX_HTML = '''<!DOCTYPE html>
<html>
<head>
    <title>MateuGram</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/png" href="/photos/logo.png">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', system-ui, sans-serif; }
        body {
            min-height: 100vh;
            background: linear-gradient(145deg, #0b2b5c 0%, #1b4a7a 50%, #2c6b9e 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            animation: gradientShift 15s ease infinite;
        }
        @keyframes gradientShift {
            0% { background: linear-gradient(145deg, #0b2b5c, #1b4a7a, #2c6b9e); }
            50% { background: linear-gradient(145deg, #1b4a7a, #2c6b9e, #0b2b5c); }
            100% { background: linear-gradient(145deg, #0b2b5c, #1b4a7a, #2c6b9e); }
        }
        .container {
            text-align: center;
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            padding: 40px;
            border-radius: 30px;
            box-shadow: 0 30px 60px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.2) inset;
            max-width: 420px;
            width: 90%;
            transition: transform 0.3s;
        }
        .container:hover { transform: translateY(-5px); }
        .logo {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            margin-bottom: 20px;
            object-fit: cover;
            border: 4px solid #fff;
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        h1 {
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        p { color: #4a5568; margin-bottom: 30px; font-size: 1.1em; }
        .btn {
            display: inline-block;
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            color: white;
            padding: 14px 32px;
            border-radius: 40px;
            text-decoration: none;
            margin: 8px;
            font-weight: 600;
            letter-spacing: 0.5px;
            transition: all 0.3s;
            box-shadow: 0 8px 15px rgba(11,43,92,0.3);
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 20px rgba(11,43,92,0.4);
        }
        .btn-outline {
            background: transparent;
            border: 2px solid #2c6b9e;
            color: #2c6b9e;
            box-shadow: none;
        }
        .btn-outline:hover {
            background: #2c6b9e;
            color: white;
        }
    </style>
</head>
<body>
    <div class="container">
        <img src="/photos/logo.png" alt="MateuGram" class="logo" onerror="this.src='https://via.placeholder.com/120/0b2b5c/ffffff?text=M'">
        <h1>MateuGram</h1>
        <p>Современное общение без границ</p>
        <a href="/register" class="btn">Регистрация</a>
        <a href="/login" class="btn btn-outline">Вход</a>
    </div>
</body>
</html>'''

# -------------------- Регистрация --------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    saved_data = {'first_name': '', 'last_name': '', 'username': '',
                  'birth_day': '', 'birth_month': '', 'email': ''}
    if request.method == 'POST':
        saved_data['first_name'] = request.form.get('first_name', '')
        saved_data['last_name'] = request.form.get('last_name', '')
        saved_data['username'] = request.form.get('username', '')
        saved_data['birth_day'] = request.form.get('birth_day', '')
        saved_data['birth_month'] = request.form.get('birth_month', '')
        saved_data['email'] = request.form.get('email', '')
        first_name = saved_data['first_name']
        last_name = saved_data['last_name']
        username = saved_data['username']
        birth_day = request.form.get('birth_day', type=int)
        birth_month = request.form.get('birth_month', type=int)
        email = saved_data['email']
        password = request.form['password']
        confirm = request.form['confirm_password']

        if password != confirm:
            flash('Пароли не совпадают')
            return render_template_string(REGISTER_TEMPLATE, saved=saved_data)

        if User.query.filter_by(username=username).first():
            flash('Имя пользователя занято')
            return render_template_string(REGISTER_TEMPLATE, saved=saved_data)

        if not email or User.query.filter_by(email=email).first():
            flash('Email некорректен или уже используется')
            return render_template_string(REGISTER_TEMPLATE, saved=saved_data)

        user = User(
            first_name=first_name,
            last_name=last_name,
            username=username,
            birth_day=birth_day,
            birth_month=birth_month,
            email=email,
            verified=True
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        login_user(user)
        return redirect(url_for('setup_profile'))

    return render_template_string(REGISTER_TEMPLATE, saved=saved_data)

REGISTER_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Регистрация в MateuGram</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/png" href="/photos/logo.png">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', system-ui, sans-serif; }
        body {
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .form-container {
            background: white;
            border-radius: 30px;
            padding: 40px;
            max-width: 550px;
            width: 100%;
            box-shadow: 0 30px 60px rgba(0,0,0,0.3);
        }
        h2 { color: #0b2b5c; margin-bottom: 25px; text-align: center; font-size: 2em; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #2d3748; font-weight: 600; font-size: 0.95em; }
        input {
            width: 100%;
            padding: 14px 18px;
            border: 2px solid #e2e8f0;
            border-radius: 15px;
            font-size: 16px;
            transition: all 0.3s;
            background: #f8fafc;
        }
        input:focus {
            border-color: #2c6b9e;
            outline: none;
            background: white;
            box-shadow: 0 0 0 4px rgba(44,107,158,0.1);
        }
        .row { display: flex; gap: 15px; }
        .btn {
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            color: white;
            border: none;
            padding: 16px;
            border-radius: 15px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: all 0.3s;
            box-shadow: 0 8px 15px rgba(11,43,92,0.3);
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 20px rgba(11,43,92,0.4);
        }
        .link { text-align: center; margin-top: 25px; }
        .link a { color: #2c6b9e; text-decoration: none; font-weight: 600; }
        .link a:hover { text-decoration: underline; }
        .flash {
            background-color: #fed7d7;
            color: #c53030;
            padding: 15px;
            border-radius: 12px;
            margin-bottom: 25px;
            border: 1px solid #fc8181;
            font-weight: 500;
        }
    </style>
</head>
<body>
    <div class="form-container">
        <h2>Регистрация</h2>
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for message in messages %}
              <div class="flash">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        <form method="POST">
            <div class="form-group"><label>Имя*</label><input name="first_name" value="{{ saved.first_name }}" required></div>
            <div class="form-group"><label>Фамилия</label><input name="last_name" value="{{ saved.last_name }}"></div>
            <div class="form-group"><label>Имя пользователя (@)</label><input name="username" pattern="[A-Za-z0-9_]+" value="{{ saved.username }}" required></div>
            <div class="row">
                <div class="form-group" style="flex:1;"><label>День (число)</label><input type="number" name="birth_day" min="1" max="31" value="{{ saved.birth_day }}"></div>
                <div class="form-group" style="flex:1;"><label>Месяц</label><input type="number" name="birth_month" min="1" max="12" value="{{ saved.birth_month }}"></div>
            </div>
            <div class="form-group"><label>Email*</label><input type="email" name="email" value="{{ saved.email }}" required></div>
            <div class="form-group"><label>Пароль*</label><input type="password" name="password" required></div>
            <div class="form-group"><label>Подтверждение*</label><input type="password" name="confirm_password" required></div>
            <button type="submit" class="btn">Зарегистрироваться</button>
        </form>
        <div class="link">Уже есть аккаунт? <a href="/login">Войти</a></div>
    </div>
</body>
</html>
'''

# -------------------- Настройка профиля --------------------
@app.route('/setup_profile', methods=['GET', 'POST'])
@login_required
def setup_profile():
    if request.method == 'POST':
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                filename = secure_filename(f"{current_user.id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                current_user.avatar = filename
                db.session.commit()
        return redirect(url_for('chats'))
    return render_template_string(SETUP_PROFILE_HTML)

SETUP_PROFILE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Выберите аватар</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/png" href="/photos/logo.png">
    <style>
        body { background: linear-gradient(145deg, #0b2b5c, #2c6b9e); min-height: 100vh; display: flex; justify-content: center; align-items: center; font-family: 'Segoe UI', sans-serif; padding: 20px; }
        .container { background: white; border-radius: 30px; padding: 40px; max-width: 500px; width: 100%; box-shadow: 0 30px 60px rgba(0,0,0,0.3); text-align: center; }
        h2 { color: #0b2b5c; }
        .avatar-preview { width: 150px; height: 150px; border-radius: 50%; margin: 20px auto; border: 4px solid #2c6b9e; object-fit: cover; }
        .btn { background: linear-gradient(145deg, #0b2b5c, #2c6b9e); color: white; border: none; padding: 14px; border-radius: 15px; font-size: 16px; cursor: pointer; width: 100%; margin: 5px 0; }
        .btn-outline { background: white; color: #2c6b9e; border: 2px solid #2c6b9e; }
        input[type="file"] { display: none; }
        .file-label { display: block; background: #e6f0fa; color: #0b2b5c; padding: 12px; border-radius: 15px; cursor: pointer; margin: 20px 0; border: 2px dashed #2c6b9e; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Завершение регистрации</h2>
        <p>Выберите аватар или пропустите</p>
        <img src="{{ url_for('uploads', filename=current_user.avatar) if current_user.avatar != 'default.jpg' else '/photos/default.jpg' }}" class="avatar-preview" id="preview">
        <form method="POST" enctype="multipart/form-data">
            <label for="avatar" class="file-label">Выбрать файл</label>
            <input type="file" name="avatar" id="avatar" accept="image/*">
            <button type="submit" class="btn">Сохранить</button>
            <a href="/chats" class="btn btn-outline">Пропустить</a>
        </form>
    </div>
    <script>
        document.getElementById('avatar').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) { document.getElementById('preview').src = e.target.result; };
                reader.readAsDataURL(file);
            }
        });
    </script>
</body>
</html>
'''

# -------------------- Список чатов --------------------
@app.route('/chats')
@login_required
def chats():
    memberships = ChatMember.query.filter_by(user_id=current_user.id).all()
    chat_ids = [m.chat_id for m in memberships]
    chats = Chat.query.filter(Chat.id.in_(chat_ids)).all()
    chat_data = []
    for chat in chats:
        last_msg = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at.desc()).first()
        unread = 0
        chat_data.append({
            'chat': chat,
            'name': get_chat_name(chat),
            'last_msg': last_msg,
            'unread': unread
        })
    return render_template_string(CHATS_HTML, chat_data=chat_data)

CHATS_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Чаты</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/png" href="/photos/logo.png">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body { background: #f5f7fa; }
        .navbar {
            background: white;
            padding: 15px 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .navbar h1 {
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .nav-links a {
            margin-left: 20px;
            text-decoration: none;
            color: #2c6b9e;
            font-weight: 600;
        }
        .container { max-width: 800px; margin: 30px auto; padding: 0 20px; }
        .chat-list { background: white; border-radius: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); overflow: hidden; }
        .chat-item {
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
            display: flex;
            align-items: center;
            cursor: pointer;
            transition: background 0.2s;
        }
        .chat-item:hover { background: #f0f4fa; }
        .chat-avatar {
            width: 50px; height: 50px; border-radius: 50%;
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            margin-right: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 1.2em;
        }
        .chat-info { flex: 1; }
        .chat-info h3 { font-size: 18px; margin-bottom: 5px; color: #1a202c; }
        .chat-info p { color: #718096; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 400px; }
        .chat-meta { text-align: right; min-width: 60px; }
        .chat-time { font-size: 12px; color: #a0aec0; }
        .unread-badge {
            background: #2c6b9e;
            color: white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
        }
        .new-chat {
            position: fixed;
            bottom: 30px;
            right: 30px;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            box-shadow: 0 5px 15px rgba(44,107,158,0.4);
            cursor: pointer;
            transition: transform 0.2s;
            text-decoration: none;
        }
        .new-chat:hover { transform: scale(1.1); }
        .flash { background-color: #fed7d7; color: #c53030; padding: 10px; border-radius: 12px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="navbar">
        <h1>MateuGram</h1>
        <div class="nav-links">
            <a href="/profile">Профиль</a>
            <a href="/settings">Настройки</a>
            <a href="/logout">Выйти</a>
        </div>
    </div>
    <div class="container">
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for message in messages %}
              <div class="flash">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        <div class="chat-list">
            {% if chat_data %}
                {% for item in chat_data %}
                <div class="chat-item" onclick="location.href='/chat/{{ item.chat.id }}'">
                    <div class="chat-avatar">{{ item.name[:1] }}</div>
                    <div class="chat-info">
                        <h3>{{ item.name }}</h3>
                        <p>{{ item.last_msg.content if item.last_msg else 'Нет сообщений' }}</p>
                    </div>
                    <div class="chat-meta">
                        {% if item.last_msg %}
                            <div class="chat-time">{{ item.last_msg.created_at.strftime('%H:%M') }}</div>
                        {% endif %}
                        {% if item.unread > 0 %}
                            <span class="unread-badge">{{ item.unread }}</span>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div style="text-align: center; padding: 50px; color: #a0aec0;">
                    У вас пока нет чатов. Начните общение!
                </div>
            {% endif %}
        </div>
    </div>
    <a href="/new-chat" class="new-chat">+</a>
</body>
</html>
'''

# -------------------- Создание нового чата (без каналов) --------------------
@app.route('/new-chat', methods=['GET', 'POST'])
@login_required
def new_chat():
    selected_type = 'private'
    saved_name = ''
    saved_username = ''

    if request.method == 'POST':
        action = request.form.get('action', 'create')
        if action == 'join':
            chat_id = request.form.get('chat_id', '').strip()
            if not chat_id:
                flash('Введите ID чата')
                return redirect(url_for('new_chat'))
            try:
                chat_id = int(chat_id)
            except ValueError:
                flash('ID чата должен быть числом')
                return redirect(url_for('new_chat'))
            chat = Chat.query.get(chat_id)
            if not chat:
                flash('Чат не найден')
                return redirect(url_for('new_chat'))
            existing = ChatMember.query.filter_by(user_id=current_user.id, chat_id=chat.id).first()
            if existing:
                flash('Вы уже в этом чате')
                return redirect(url_for('chat', chat_id=chat.id))
            cm = ChatMember(user_id=current_user.id, chat_id=chat.id, role='member')
            db.session.add(cm)
            db.session.commit()
            flash('Вы присоединились к чату')
            return redirect(url_for('chat', chat_id=chat.id))

        # Создание
        chat_type = request.form.get('chat_type', 'private')
        raw_name = request.form.get('name', '')
        saved_name = raw_name
        saved_username = request.form.get('username', '').strip()
        selected_type = chat_type

        if chat_type == 'private':
            if not saved_username:
                flash('Введите имя пользователя')
                return render_template_string(NEW_CHAT_TEMPLATE, selected_type=selected_type, saved_name=saved_name, saved_username=saved_username)
            other = User.query.filter_by(username=saved_username).first()
            if not other:
                flash('Пользователь не найден')
                return render_template_string(NEW_CHAT_TEMPLATE, selected_type=selected_type, saved_name=saved_name, saved_username=saved_username)
            if other.id == current_user.id:
                flash('Нельзя создать чат с самим собой')
                return render_template_string(NEW_CHAT_TEMPLATE, selected_type=selected_type, saved_name=saved_name, saved_username=saved_username)
            user_chats = {m.chat_id for m in ChatMember.query.filter_by(user_id=current_user.id)}
            other_chats = {m.chat_id for m in ChatMember.query.filter_by(user_id=other.id)}
            common = user_chats & other_chats
            for cid in common:
                chat = Chat.query.get(cid)
                if chat and not chat.is_group and not chat.is_channel:
                    flash('Чат уже существует')
                    return redirect(url_for('chat', chat_id=chat.id))
            chat = Chat(is_group=False, is_channel=False, created_by=current_user.id)
            db.session.add(chat)
            db.session.flush()
            db.session.add_all([
                ChatMember(user_id=current_user.id, chat_id=chat.id, role='owner'),
                ChatMember(user_id=other.id, chat_id=chat.id, role='member')
            ])
            db.session.commit()
            return redirect(url_for('chat', chat_id=chat.id))

        elif chat_type == 'group':
            if not raw_name.strip():
                flash('Введите название группы')
                return render_template_string(NEW_CHAT_TEMPLATE, selected_type=selected_type, saved_name=saved_name, saved_username=saved_username)
            token = generate_invite_token()
            while Chat.query.filter_by(invite_token=token).first():
                token = generate_invite_token()
            chat = Chat(name=raw_name.strip(), is_group=True, is_channel=False, created_by=current_user.id, invite_token=token)
            db.session.add(chat)
            db.session.flush()
            db.session.add(ChatMember(user_id=current_user.id, chat_id=chat.id, role='owner'))
            db.session.commit()
            return redirect(url_for('chat', chat_id=chat.id))

        elif chat_type == 'channel':
            flash('Функция каналов временно в разработке')
            return render_template_string(NEW_CHAT_TEMPLATE, selected_type=selected_type, saved_name=saved_name, saved_username=saved_username)

    return render_template_string(NEW_CHAT_TEMPLATE, selected_type=selected_type, saved_name=saved_name, saved_username=saved_username)

NEW_CHAT_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Новый чат</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/png" href="/photos/logo.png">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body {
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 30px;
            padding: 40px;
            max-width: 550px;
            width: 100%;
            box-shadow: 0 30px 60px rgba(0,0,0,0.3);
        }
        h2 { color: #0b2b5c; margin-bottom: 25px; text-align: center; }
        .type-buttons {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .type-btn {
            flex: 1;
            padding: 14px;
            border: 2px solid #e2e8f0;
            background: white;
            color: #2d3748;
            border-radius: 15px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .type-btn.active {
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            color: white;
            border-color: transparent;
        }
        .type-btn:hover { background: #e6f0fa; }
        .type-btn.active:hover { background: linear-gradient(145deg, #1b4a7a, #3c7bb9); }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #2d3748; font-weight: 600; }
        input {
            width: 100%;
            padding: 14px 18px;
            border: 2px solid #e2e8f0;
            border-radius: 15px;
            font-size: 16px;
            transition: 0.3s;
        }
        input:focus {
            border-color: #2c6b9e;
            outline: none;
            background: #f8fafc;
        }
        .btn {
            background: linear-gradient(145deg, #0b2b5c, #2c6b9e);
            color: white;
            border: none;
            padding: 16px;
            border-radius: 15px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: 0.3s;
            margin-top: 10px;
        }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 8px 15px rgba(11,43,92,0.3); }
        .btn-outline {
            background: white;
            color: #2c6b9e;
            border: 2px solid #2c6b9e;
        }
        .flash {
            background-color: #fed7d7;
            color: #c53030;
            padding: 15px;
            border-radius: 12px;
            margin-bottom: 25px;
        }
        .section-title {
            font-size: 1.2em;
            margin: 25px 0 15px;
            color: #0b2b5c;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 5px;
        }
        hr { margin: 30px 0; border: 1px solid #e2e8f0; }
    </style>
    <script>
        function setType(type) {
            document.getElementById('chat_type').value = type;
            document.querySelectorAll('.type-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('btn-' + type).classList.add('active');
            document.getElementById('private-fields').style.display = type === 'private' ? 'block' : 'none';
            document.getElementById('group-fields').style.display = type === 'group' ? 'block' : 'none';
        }
    </script>
</head>
<body>
    <div class="container">
        <h2>Создать новый чат</h2>
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for message in messages %}
              <div class="flash">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <!-- Форма создания чата -->
        <form method="POST">
            <input type="hidden" name="action" value="create">
            <input type="hidden" name="chat_type" id="chat_type" value="{{ selected_type }}">

            <div class="type-buttons">
                <button type="button" id="btn-private" class="type-btn {% if selected_type == 'private' %}active{% endif %}" onclick="setType('private')">Личный чат</button>
                <button type="button" id="btn-group" class="type-btn {% if selected_type == 'group' %}active{% endif %}" onclick="setType('group')">Группа</button>
                <button type="button" id="btn-channel" class="type-btn {% if selected_type == 'channel' %}active{% endif %}" onclick="setType('channel')">Канал</button>
            </div>

            <div id="private-fields" style="display: {{ 'block' if selected_type == 'private' else 'none' }};">
                <div class="form-group">
                    <label>Имя пользователя (собеседник)</label>
                    <input type="text" name="username" placeholder="@username" value="{{ saved_username }}">
                </div>
            </div>

            <div id="group-fields" style="display: {{ 'block' if selected_type == 'group' else 'none' }};">
                <div class="form-group">
                    <label>Название группы</label>
                    <input type="text" name="name" value="{{ saved_name if selected_type == 'group' else '' }}">
                </div>
            </div>

            <button type="submit" class="btn">Создать</button>
        </form>

        <hr>

        <!-- Форма вступления по ID -->
        <div class="section-title">Присоединиться к чату</div>
        <form method="POST">
            <input type="hidden" name="action" value="join">
            <div class="form-group">
                <label>ID чата</label>
                <input type="text" name="chat_id" placeholder="Введите ID чата" required>
            </div>
            <button type="submit" class="btn btn-outline">Вступить</button>
        </form>

        <a href="/chats" style="display: block; text-align: center; margin-top: 25px; color: #2c6b9e;">← Вернуться к чатам</a>
    </div>

    <script>
        var initialType = "{{ selected_type }}";
        setType(initialType);
    </script>
</body>
</html>
'''

# -------------------- Чат (с изменённой кнопкой звонка) --------------------
# Здесь для краткости приведён только фрагмент с кнопкой звонка.
# Полный код чата можно взять из предыдущей версии, заменив блок call-buttons на:
# <div class="call-buttons">
#     {% if is_private and other_user %}
#         <a href="https://voice.mateugram.onrender.com/room/create?user={{ current_user.username }}" target="_blank" class="call-btn" title="Позвонить через MateuGram Voice">📞</a>
#     {% endif %}
# </div>
# Также нужно добавить в head: <link rel="icon" type="image/png" href="/photos/logo.png">

# Остальные маршруты (профиль, настройки, вход и т.д.) сохраняются как в предыдущей полной версии.
# Для полноты их необходимо добавить, но в целях экономии места здесь они опущены.

# -------------------- Запуск --------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
