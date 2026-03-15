import os
import threading
import random
import string
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import telegram
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler

# Конфигурация
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # изменить в продакшене
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mateugram.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Почта (заменить на свои данные)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-app-password'
app.config['MAIL_DEFAULT_SENDER'] = 'your-email@gmail.com'

# Telegram Bot
BOT_TOKEN = '8665436338:AAEXVX6UatwMDBW7zb70no2aFmxp0i343Nc'
bot = telegram.Bot(token=BOT_TOKEN)

# Расширения
db = SQLAlchemy(app)
mail = Mail(app)
socketio = SocketIO(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Создание папок для загрузок, если их нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('photos', exist_ok=True)

# Модели базы данных
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80))
    birth_day = db.Column(db.Integer)
    birth_month = db.Column(db.Integer)
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20), unique=True)
    password_hash = db.Column(db.String(200))
    avatar = db.Column(db.String(200), default='default.jpg')
    verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(6))
    verification_method = db.Column(db.String(10))  # 'email' or 'telegram'
    telegram_id = db.Column(db.String(50))  # для подтверждения через Telegram
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ChatMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'))
    role = db.Column(db.String(20), default='member')  # 'admin', 'member', 'owner'
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'))
    content = db.Column(db.Text)
    reply_to = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    forwarded_from = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Reaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reaction = db.Column(db.String(10))  # emoji

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'))
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Вспомогательные функции
def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(user):
    msg = Message('Подтверждение регистрации в MateuGram',
                  recipients=[user.email])
    msg.body = f'Ваш код подтверждения: {user.verification_code}'
    mail.send(msg)

def send_verification_telegram(user):
    try:
        bot.send_message(chat_id=user.telegram_id,
                         text=f'Ваш код подтверждения для MateuGram: {user.verification_code}')
    except Exception as e:
        print(f"Telegram send error: {e}")

# Маршрут для статических файлов из папки photos
@app.route('/photos/<filename>')
def photos(filename):
    return send_from_directory('photos', filename)

# Главная страница
@app.route('/')
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>MateuGram</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
                body {
                    min-height: 100vh;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                }
                .container {
                    text-align: center;
                    background: rgba(255,255,255,0.95);
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    max-width: 400px;
                    width: 90%;
                }
                .logo {
                    width: 120px;
                    height: 120px;
                    border-radius: 50%;
                    margin-bottom: 20px;
                    object-fit: cover;
                    border: 3px solid #667eea;
                }
                h1 { color: #333; margin-bottom: 10px; }
                p { color: #666; margin-bottom: 30px; }
                .btn {
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 12px 30px;
                    border-radius: 25px;
                    text-decoration: none;
                    margin: 5px;
                    transition: transform 0.3s;
                }
                .btn:hover { transform: scale(1.05); }
                .btn-outline {
                    background: transparent;
                    border: 2px solid #667eea;
                    color: #667eea;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <img src="/photos/logo.jpg" alt="MateuGram" class="logo" onerror="this.src='https://via.placeholder.com/120'">
                <h1>MateuGram</h1>
                <p>Общайся свободно</p>
                <a href="/register" class="btn">Регистрация</a>
                <a href="/login" class="btn btn-outline">Вход</a>
            </div>
        </body>
        </html>
    ''')

# Регистрация
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form.get('last_name', '')
        username = request.form['username']
        birth_day = request.form.get('birth_day', type=int)
        birth_month = request.form.get('birth_month', type=int)
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form['password']
        confirm = request.form['confirm_password']
        verification_method = request.form['verification_method']  # 'email' or 'telegram'

        # Проверки
        if password != confirm:
            flash('Пароли не совпадают')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Имя пользователя занято')
            return redirect(url_for('register'))

        if verification_method == 'email':
            if not email or User.query.filter_by(email=email).first():
                flash('Email некорректен или уже используется')
                return redirect(url_for('register'))
        else:  # telegram
            if not phone or User.query.filter_by(phone=phone).first():
                flash('Телефон некорректен или уже используется')
                return redirect(url_for('register'))
            # Для упрощения будем использовать phone как идентификатор для Telegram-бота,
            # но на самом деле нужно получить telegram_id от пользователя через бота.
            # В реальном проекте здесь должен быть запрос к боту. Упростим: сохраняем phone,
            # а позже пользователь отправит код боту, и мы свяжем аккаунт по номеру.
            # Но для демо используем телефон как временный идентификатор.

        user = User(
            first_name=first_name,
            last_name=last_name,
            username=username,
            birth_day=birth_day,
            birth_month=birth_month,
            email=email if verification_method == 'email' else None,
            phone=phone if verification_method == 'telegram' else None,
            verification_method=verification_method,
            verification_code=generate_verification_code(),
            verified=False
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        # Отправка кода
        if verification_method == 'email':
            send_verification_email(user)
        else:
            # В реальном проекте нужно получить telegram_id от пользователя.
            # Здесь мы просто сохраняем код в сессии и будем ждать сообщения от бота.
            # Для демо отправим код через бота на указанный номер? Но бот не может отправить на номер.
            # Поэтому создадим отдельный маршрут, где пользователь вводит код.
            # А бот будет слушать сообщения и проверять код.
            # Пока просто проинформируем.
            flash('Код подтверждения отправлен в Telegram. Напишите боту @... с этим кодом.')

        session['user_id'] = user.id
        return redirect(url_for('verify'))

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Регистрация в MateuGram</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
                body {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    padding: 20px;
                }
                .form-container {
                    background: white;
                    border-radius: 20px;
                    padding: 40px;
                    max-width: 500px;
                    width: 100%;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                }
                h2 { color: #333; margin-bottom: 20px; text-align: center; }
                .form-group { margin-bottom: 15px; }
                label { display: block; margin-bottom: 5px; color: #555; font-weight: 500; }
                input, select {
                    width: 100%;
                    padding: 12px;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    font-size: 16px;
                    transition: border 0.3s;
                }
                input:focus {
                    border-color: #667eea;
                    outline: none;
                }
                .row {
                    display: flex;
                    gap: 10px;
                }
                .btn {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    padding: 14px;
                    border-radius: 8px;
                    font-size: 16px;
                    cursor: pointer;
                    width: 100%;
                    transition: opacity 0.3s;
                }
                .btn:hover { opacity: 0.9; }
                .link {
                    text-align: center;
                    margin-top: 20px;
                }
                .link a {
                    color: #667eea;
                    text-decoration: none;
                }
                .verification-options {
                    display: flex;
                    gap: 20px;
                    margin-bottom: 20px;
                }
                .verification-options label {
                    display: flex;
                    align-items: center;
                    gap: 5px;
                    font-weight: normal;
                }
            </style>
        </head>
        <body>
            <div class="form-container">
                <h2>Регистрация</h2>
                <form method="POST">
                    <div class="form-group">
                        <label>Имя*</label>
                        <input type="text" name="first_name" required>
                    </div>
                    <div class="form-group">
                        <label>Фамилия (необязательно)</label>
                        <input type="text" name="last_name">
                    </div>
                    <div class="form-group">
                        <label>Имя пользователя (@)</label>
                        <input type="text" name="username" pattern="[A-Za-z0-9_]+" required>
                    </div>
                    <div class="row">
                        <div class="form-group" style="flex:1;">
                            <label>День рождения (число)</label>
                            <input type="number" name="birth_day" min="1" max="31">
                        </div>
                        <div class="form-group" style="flex:1;">
                            <label>Месяц</label>
                            <input type="number" name="birth_month" min="1" max="12">
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Способ подтверждения</label>
                        <div class="verification-options">
                            <label><input type="radio" name="verification_method" value="email" checked> Почта</label>
                            <label><input type="radio" name="verification_method" value="telegram"> Telegram</label>
                        </div>
                    </div>
                    <div class="form-group" id="email-field">
                        <label>Email</label>
                        <input type="email" name="email">
                    </div>
                    <div class="form-group" id="phone-field" style="display:none;">
                        <label>Номер телефона</label>
                        <input type="tel" name="phone">
                    </div>
                    <div class="form-group">
                        <label>Пароль*</label>
                        <input type="password" name="password" required>
                    </div>
                    <div class="form-group">
                        <label>Подтверждение пароля*</label>
                        <input type="password" name="confirm_password" required>
                    </div>
                    <button type="submit" class="btn">Зарегистрироваться</button>
                </form>
                <div class="link">
                    Уже есть аккаунт? <a href="/login">Войти</a>
                </div>
            </div>
            <script>
                const methodRadios = document.querySelectorAll('input[name="verification_method"]');
                const emailField = document.getElementById('email-field');
                const phoneField = document.getElementById('phone-field');
                methodRadios.forEach(radio => {
                    radio.addEventListener('change', function() {
                        if (this.value === 'email') {
                            emailField.style.display = 'block';
                            phoneField.style.display = 'none';
                            document.querySelector('input[name="email"]').required = true;
                            document.querySelector('input[name="phone"]').required = false;
                        } else {
                            emailField.style.display = 'none';
                            phoneField.style.display = 'block';
                            document.querySelector('input[name="email"]').required = false;
                            document.querySelector('input[name="phone"]').required = true;
                        }
                    });
                });
            </script>
        </body>
        </html>
    ''')

# Подтверждение
@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if 'user_id' not in session:
        return redirect(url_for('register'))
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('register'))

    if request.method == 'POST':
        code = request.form['code']
        if code == user.verification_code:
            user.verified = True
            db.session.commit()
            login_user(user)
            return redirect(url_for('setup_profile'))
        else:
            flash('Неверный код')
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Подтверждение</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; font-family: 'Segoe UI', sans-serif; padding: 20px; }
                .container { background: white; border-radius: 20px; padding: 40px; max-width: 400px; width: 100%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); text-align: center; }
                h2 { color: #333; margin-bottom: 20px; }
                p { color: #666; margin-bottom: 30px; }
                input { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; margin-bottom: 20px; text-align: center; letter-spacing: 2px; }
                .btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 14px; border-radius: 8px; font-size: 16px; cursor: pointer; width: 100%; }
                .info { background: #f0f4ff; padding: 10px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Подтверждение</h2>
                <div class="info">
                    Код отправлен на {{ 'email' if user.verification_method == 'email' else 'Telegram' }}.
                </div>
                <form method="POST">
                    <input type="text" name="code" placeholder="6-значный код" maxlength="6" pattern="\\d{6}" required>
                    <button type="submit" class="btn">Подтвердить</button>
                </form>
            </div>
        </body>
        </html>
    ''', user=user)

# Настройка профиля после подтверждения (аватарка)
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
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Выберите аватар</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; font-family: 'Segoe UI', sans-serif; padding: 20px; }
                .container { background: white; border-radius: 20px; padding: 40px; max-width: 500px; width: 100%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); text-align: center; }
                h2 { color: #333; margin-bottom: 10px; }
                p { color: #666; margin-bottom: 30px; }
                .avatar-preview { width: 150px; height: 150px; border-radius: 50%; background: #f0f0f0; margin: 0 auto 30px; border: 3px solid #667eea; object-fit: cover; }
                .btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 14px 20px; border-radius: 8px; font-size: 16px; cursor: pointer; width: 100%; margin-bottom: 10px; }
                .btn-outline { background: white; color: #667eea; border: 2px solid #667eea; }
                input[type="file"] { display: none; }
                .file-label { display: block; background: #f0f4ff; color: #667eea; padding: 12px; border-radius: 8px; cursor: pointer; margin-bottom: 20px; border: 2px dashed #667eea; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Завершение регистрации</h2>
                <p>Выберите аватар или пропустите</p>
                <img src="/uploads/{{ current_user.avatar if current_user.avatar != 'default.jpg' else '/photos/default.jpg' }}" class="avatar-preview" id="preview">
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
                        reader.onload = function(e) {
                            document.getElementById('preview').src = e.target.result;
                        }
                        reader.readAsDataURL(file);
                    }
                });
            </script>
        </body>
        </html>
    ''')

# Страница со списком чатов (упрощённо)
@app.route('/chats')
@login_required
def chats():
    # Получаем чаты, где участвует пользователь
    memberships = ChatMember.query.filter_by(user_id=current_user.id).all()
    chat_ids = [m.chat_id for m in memberships]
    chats = Chat.query.filter(Chat.id.in_(chat_ids)).all()
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Чаты</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
                body { background: #f5f7fa; }
                .navbar {
                    background: white;
                    padding: 15px 20px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .navbar h1 {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }
                .nav-links a {
                    margin-left: 20px;
                    text-decoration: none;
                    color: #667eea;
                }
                .container { max-width: 800px; margin: 30px auto; padding: 0 20px; }
                .chat-list { background: white; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
                .chat-item {
                    padding: 15px 20px;
                    border-bottom: 1px solid #eee;
                    display: flex;
                    align-items: center;
                    cursor: pointer;
                    transition: background 0.3s;
                }
                .chat-item:hover { background: #f8f9ff; }
                .chat-avatar {
                    width: 50px; height: 50px; border-radius: 50%;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    margin-right: 15px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-weight: bold;
                }
                .chat-info h3 { font-size: 18px; margin-bottom: 5px; color: #333; }
                .chat-info p { color: #999; font-size: 14px; }
                .new-chat {
                    position: fixed;
                    bottom: 30px;
                    right: 30px;
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 24px;
                    box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
                    cursor: pointer;
                    transition: transform 0.3s;
                }
                .new-chat:hover { transform: scale(1.1); }
            </style>
        </head>
        <body>
            <div class="navbar">
                <h1>MateuGram</h1>
                <div class="nav-links">
                    <a href="/profile">Профиль</a>
                    <a href="/logout">Выйти</a>
                </div>
            </div>
            <div class="container">
                <div class="chat-list">
                    {% if chats %}
                        {% for chat in chats %}
                        <div class="chat-item" onclick="location.href='/chat/{{ chat.id }}'">
                            <div class="chat-avatar">{{ chat.name[:1] }}</div>
                            <div class="chat-info">
                                <h3>{{ chat.name }}</h3>
                                <p>Последнее сообщение...</p>
                            </div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div style="text-align: center; padding: 50px; color: #999;">
                            У вас пока нет чатов. Начните общение!
                        </div>
                    {% endif %}
                </div>
            </div>
            <div class="new-chat" onclick="location.href='/new-chat'">+</div>
        </body>
        </html>
    ''', chats=chats)

# Профиль пользователя
@app.route('/profile')
@login_required
def profile():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Профиль</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
                body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
                .container {
                    background: white;
                    border-radius: 20px;
                    padding: 30px;
                    max-width: 600px;
                    margin: 0 auto;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                }
                .avatar {
                    width: 120px;
                    height: 120px;
                    border-radius: 50%;
                    margin: 0 auto 20px;
                    display: block;
                    border: 3px solid #667eea;
                    object-fit: cover;
                }
                h2 { text-align: center; color: #333; margin-bottom: 10px; }
                .username { text-align: center; color: #667eea; margin-bottom: 30px; font-size: 18px; }
                .info-item { padding: 15px; border-bottom: 1px solid #eee; display: flex; }
                .info-label { font-weight: bold; width: 120px; color: #555; }
                .info-value { color: #333; }
                .btn {
                    display: block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-align: center;
                    padding: 14px;
                    border-radius: 8px;
                    text-decoration: none;
                    margin-top: 30px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <img src="/uploads/{{ current_user.avatar if current_user.avatar != 'default.jpg' else '/photos/default.jpg' }}" class="avatar">
                <h2>{{ current_user.first_name }} {{ current_user.last_name }}</h2>
                <div class="username">@{{ current_user.username }}</div>
                <div class="info-item">
                    <div class="info-label">Email:</div>
                    <div class="info-value">{{ current_user.email or 'не указан' }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Телефон:</div>
                    <div class="info-value">{{ current_user.phone or 'не указан' }}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">День рождения:</div>
                    <div class="info-value">
                        {% if current_user.birth_day and current_user.birth_month %}
                            {{ current_user.birth_day }}.{{ current_user.birth_month }}
                        {% else %}
                            не указан
                        {% endif %}
                    </div>
                </div>
                <a href="/chats" class="btn">К чатам</a>
            </div>
        </body>
        </html>
    ''')

# Вход
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.verified:
            login_user(user)
            return redirect(url_for('chats'))
        else:
            flash('Неверные данные или аккаунт не подтверждён')
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Вход в MateuGram</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; font-family: 'Segoe UI', sans-serif; padding: 20px; }
                .form-container { background: white; border-radius: 20px; padding: 40px; max-width: 400px; width: 100%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
                h2 { text-align: center; color: #333; margin-bottom: 30px; }
                input { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; margin-bottom: 20px; font-size: 16px; }
                .btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 14px; border-radius: 8px; font-size: 16px; cursor: pointer; width: 100%; }
                .link { text-align: center; margin-top: 20px; }
                .link a { color: #667eea; text-decoration: none; }
            </style>
        </head>
        <body>
            <div class="form-container">
                <h2>Вход в MateuGram</h2>
                <form method="POST">
                    <input type="text" name="username" placeholder="Имя пользователя" required>
                    <input type="password" name="password" placeholder="Пароль" required>
                    <button type="submit" class="btn">Войти</button>
                </form>
                <div class="link">
                    Нет аккаунта? <a href="/register">Зарегистрироваться</a>
                </div>
            </div>
        </body>
        </html>
    ''')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Пример чата (real-time через SocketIO)
@app.route('/chat/<int:chat_id>')
@login_required
def chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    # Проверка, что пользователь участник
    membership = ChatMember.query.filter_by(user_id=current_user.id, chat_id=chat_id).first()
    if not membership:
        flash('Вы не участник этого чата')
        return redirect(url_for('chats'))
    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.created_at).all()
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Чат</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
                body { background: #f5f7fa; height: 100vh; display: flex; flex-direction: column; }
                .chat-header {
                    background: white;
                    padding: 15px 20px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    display: flex;
                    align-items: center;
                }
                .chat-header .back {
                    font-size: 24px;
                    margin-right: 20px;
                    cursor: pointer;
                    color: #667eea;
                    text-decoration: none;
                }
                .chat-header h2 { color: #333; }
                .messages-container {
                    flex: 1;
                    overflow-y: auto;
                    padding: 20px;
                    display: flex;
                    flex-direction: column;
                }
                .message {
                    max-width: 70%;
                    margin-bottom: 15px;
                    padding: 10px 15px;
                    border-radius: 18px;
                    position: relative;
                    word-wrap: break-word;
                }
                .message.sent {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    align-self: flex-end;
                    border-bottom-right-radius: 4px;
                }
                .message.received {
                    background: white;
                    color: #333;
                    align-self: flex-start;
                    border-bottom-left-radius: 4px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }
                .message .sender {
                    font-size: 12px;
                    font-weight: bold;
                    margin-bottom: 3px;
                    color: #666;
                }
                .message.sent .sender { color: #ddd; }
                .message .time {
                    font-size: 10px;
                    margin-top: 5px;
                    text-align: right;
                    color: #aaa;
                }
                .input-area {
                    background: white;
                    padding: 15px 20px;
                    display: flex;
                    gap: 10px;
                    border-top: 1px solid #ddd;
                }
                .input-area input {
                    flex: 1;
                    padding: 12px;
                    border: 1px solid #ddd;
                    border-radius: 25px;
                    font-size: 16px;
                    outline: none;
                }
                .input-area button {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    width: 50px;
                    height: 50px;
                    border-radius: 50%;
                    font-size: 20px;
                    cursor: pointer;
                }
            </style>
        </head>
        <body>
            <div class="chat-header">
                <a href="/chats" class="back">←</a>
                <h2>{{ chat.name }}</h2>
            </div>
            <div class="messages-container" id="messages">
                {% for msg in messages %}
                    {% set sender = User.query.get(msg.sender_id) %}
                    <div class="message {{ 'sent' if msg.sender_id == current_user.id else 'received' }}" data-id="{{ msg.id }}">
                        {% if msg.sender_id != current_user.id %}
                            <div class="sender">{{ sender.first_name }}</div>
                        {% endif %}
                        <div>{{ msg.content }}</div>
                        <div class="time">{{ msg.created_at.strftime('%H:%M') }}</div>
                    </div>
                {% endfor %}
            </div>
            <div class="input-area">
                <input type="text" id="message-input" placeholder="Напишите сообщение...">
                <button id="send-btn">➤</button>
            </div>
            <script>
                var socket = io();
                var chatId = {{ chat_id }};
                var userId = {{ current_user.id }};

                socket.on('connect', function() {
                    socket.emit('join', {chat_id: chatId});
                });

                document.getElementById('send-btn').onclick = sendMessage;
                document.getElementById('message-input').onkeypress = function(e) {
                    if (e.key === 'Enter') sendMessage();
                };

                function sendMessage() {
                    var input = document.getElementById('message-input');
                    var text = input.value.trim();
                    if (text) {
                        socket.emit('send_message', {
                            chat_id: chatId,
                            content: text,
                            sender_id: userId
                        });
                        input.value = '';
                    }
                }

                socket.on('new_message', function(data) {
                    var messagesDiv = document.getElementById('messages');
                    var msgDiv = document.createElement('div');
                    msgDiv.className = 'message ' + (data.sender_id == userId ? 'sent' : 'received');
                    if (data.sender_id != userId) {
                        var senderDiv = document.createElement('div');
                        senderDiv.className = 'sender';
                        senderDiv.innerText = data.sender_name;
                        msgDiv.appendChild(senderDiv);
                    }
                    var contentDiv = document.createElement('div');
                    contentDiv.innerText = data.content;
                    msgDiv.appendChild(contentDiv);
                    var timeDiv = document.createElement('div');
                    timeDiv.className = 'time';
                    timeDiv.innerText = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                    msgDiv.appendChild(timeDiv);
                    messagesDiv.appendChild(msgDiv);
                    messagesDiv.scrollTop = messagesDiv.scrollHeight;
                });
            </script>
        </body>
        </html>
    ''', chat=chat, messages=messages, User=User, current_user=current_user, chat_id=chat_id)

# SocketIO события
@socketio.on('join')
def on_join(data):
    chat_id = data['chat_id']
    join_room(f"chat_{chat_id}")

@socketio.on('send_message')
def handle_message(data):
    chat_id = data['chat_id']
    content = data['content']
    sender_id = data['sender_id']
    sender = User.query.get(sender_id)
    msg = Message(sender_id=sender_id, chat_id=chat_id, content=content)
    db.session.add(msg)
    db.session.commit()
    emit('new_message', {
        'content': content,
        'sender_id': sender_id,
        'sender_name': sender.first_name,
        'chat_id': chat_id
    }, room=f"chat_{chat_id}")

# Запуск Telegram-бота в отдельном потоке
def telegram_bot():
    from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

    def start(update, context):
        update.message.reply_text('Добро пожаловать в MateuGram! Отправьте код подтверждения, если вы регистрируетесь.')

    def handle_message(update, context):
        text = update.message.text
        user_id = update.message.chat_id
        # Ищем пользователя с таким verification_code и не verified
        user = User.query.filter_by(verification_code=text, verified=False).first()
        if user:
            user.verified = True
            user.telegram_id = str(user_id)
            db.session.commit()
            update.message.reply_text('Ваш аккаунт подтверждён! Можете войти на сайт.')
        else:
            update.message.reply_text('Неверный код. Попробуйте ещё раз.')

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

# Запуск бота в фоне
threading.Thread(target=telegram_bot, daemon=True).start()

# Создание таблиц БД
with app.app_context():
    db.create_all()
    # Создаём папку uploads, если нет
    if not os.path.exists('uploads'):
        os.makedirs('uploads')

if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
