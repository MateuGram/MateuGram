"""
MateuGram - Синяя социальная сеть
Версия с функциями редактирования профиля, загрузкой фото/видео, смайликами
"""

from flask import Flask, render_template_string, request, redirect, url_for, flash, get_flashed_messages, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import re
import secrets
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ========== НАСТРОЙКА ПРИЛОЖЕНИЯ ==========
app = Flask(__name__)

# Настройки приложения
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mateugram-secret-key-2024-change-this')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///mateugram_admin.db').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Настройки для загрузки файлов
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB максимум для видео
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'mkv'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

# Создаем папку для загрузок, если она не существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ========== МОДЕЛИ БАЗЫ ДАННЫХ ==========
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(6))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    bio = db.Column(db.Text, default='')
    avatar_filename = db.Column(db.String(200), default='default_avatar.png')
    
    posts = db.relationship('Post', backref='author', lazy=True, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy=True, cascade='all, delete-orphan')
    
    blocked_users = db.relationship('BlockedUser', foreign_keys='BlockedUser.blocker_id', backref='blocker', lazy=True)
    blocked_by = db.relationship('BlockedUser', foreign_keys='BlockedUser.blocked_id', backref='blocked', lazy=True)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_type = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports_count = db.Column(db.Integer, default=0)
    reported_by = db.Column(db.Text, default='')
    is_hidden = db.Column(db.Boolean, default=False)
    
    # Медиа файлы
    images = db.Column(db.Text, default='')  # JSON список изображений
    videos = db.Column(db.Text, default='')  # JSON список видео
    
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy=True, cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports_count = db.Column(db.Integer, default=0)
    reported_by = db.Column(db.Text, default='')
    is_hidden = db.Column(db.Boolean, default=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_like'),)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    reports_count = db.Column(db.Integer, default=0)
    reported_by = db.Column(db.Text, default='')
    is_hidden = db.Column(db.Boolean, default=False)

class BlockedUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('blocker_id', 'blocked_id', name='unique_block'),)

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    if user and user.is_active and not user.is_banned:
        return user
    return None

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def validate_username(username):
    pattern = r'^[a-zA-Z0-9_.-]+$'
    return bool(re.match(pattern, username))

def check_content_for_report(content):
    """Проверяет контент на наличие запрещенных слов"""
    forbidden_words = ['мат', 'нецензурное', 'сленг', 'политика', 'религия']
    content_lower = content.lower()
    found_words = []
    
    for word in forbidden_words:
        if word in content_lower:
            found_words.append(word)
    
    return len(found_words) == 0, found_words

def allowed_file(filename, file_type='image'):
    """Проверяет разрешен ли файл"""
    if '.' not in filename:
        return False
    
    ext = filename.rsplit('.', 1)[1].lower()
    
    if file_type == 'image':
        return ext in ALLOWED_IMAGE_EXTENSIONS
    elif file_type == 'video':
        return ext in ALLOWED_VIDEO_EXTENSIONS
    else:
        return ext in ALLOWED_EXTENSIONS

def save_file(file, file_type='image'):
    """Сохраняет файл на сервере"""
    if file and allowed_file(file.filename, file_type):
        filename = secure_filename(file.filename)
        unique_filename = f"{secrets.token_hex(8)}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        return unique_filename
    return None

def parse_media_list(media_string):
    """Парсит JSON строку с медиа файлами"""
    import json
    try:
        if media_string:
            return json.loads(media_string)
    except:
        pass
    return []

def save_media_files(files, max_files, file_type='image'):
    """Сохраняет несколько медиа файлов"""
    saved_files = []
    count = 0
    
    for file in files:
        if file.filename == '':
            continue
            
        if count >= max_files:
            break
            
        saved_name = save_file(file, file_type)
        if saved_name:
            saved_files.append(saved_name)
            count += 1
    
    return saved_files

def get_emoji_html(content):
    """Заменяет смайлики на изображения или оставляет как есть"""
    emoji_map = {
        ':)': '😊', ':(': '😔', ':D': '😃', ':P': '😛', ';)': '😉',
        ':/': '😕', ':O': '😮', ':*': '😘', '<3': '❤️', '</3': '💔',
        ':+1:': '👍', ':-1:': '👎', ':fire:': '🔥', ':100:': '💯'
    }
    
    for code, emoji in emoji_map.items():
        content = content.replace(code, emoji)
    
    return content

# ========== HTML ШАБЛОНЫ ==========
BASE_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MateuGram - {title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            color: #333;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .header h1 {{
            color: #2a5298;
            margin-bottom: 10px;
            font-size: 2.5em;
        }}
        .header p {{
            color: #666;
            font-size: 1.1em;
        }}
        .card {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .form-group {{
            margin-bottom: 20px;
        }}
        .form-label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #444;
        }}
        .form-input {{
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }}
        .form-input:focus {{
            border-color: #2a5298;
            outline: none;
        }}
        .btn {{
            background: linear-gradient(135deg, #2a5298 0%, #1e3c72 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            text-decoration: none;
            display: inline-block;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(42, 82, 152, 0.3);
        }}
        .emoji-picker {{
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 10px;
            margin: 10px 0;
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            max-height: 150px;
            overflow-y: auto;
        }}
        .emoji-btn {{
            font-size: 20px;
            background: none;
            border: none;
            cursor: pointer;
            padding: 5px;
            border-radius: 5px;
        }}
        .emoji-btn:hover {{
            background: #f0f0f0;
        }}
        .media-preview {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 10px 0;
        }}
        .media-item {{
            position: relative;
            width: 100px;
            height: 100px;
            border-radius: 8px;
            overflow: hidden;
        }}
        .media-item img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .media-item video {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .remove-media {{
            position: absolute;
            top: 5px;
            right: 5px;
            background: rgba(255, 0, 0, 0.7);
            color: white;
            border: none;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            cursor: pointer;
            font-size: 12px;
        }}
        .media-gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 10px;
            margin: 15px 0;
        }}
        .gallery-item {{
            border-radius: 8px;
            overflow: hidden;
        }}
        .gallery-item img {{
            width: 100%;
            height: 200px;
            object-fit: cover;
        }}
        .gallery-item video {{
            width: 100%;
            height: 200px;
            object-fit: cover;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔵 MateuGram</h1>
            <p>Синяя социальная сеть для безопасного общения</p>
        </div>
        
        {flash_messages}
        
        {content}
    </div>
    
    <script>
    function toggleEmojiPicker(elementId) {{
        const picker = document.getElementById(elementId + '-picker');
        if (picker.style.display === 'none' || picker.style.display === '') {{
            picker.style.display = 'block';
        }} else {{
            picker.style.display = 'none';
        }}
    }}
    
    function insertEmoji(elementId, emoji) {{
        const input = document.getElementById(elementId);
        input.value += emoji;
    }}
    
    function previewMedia(input, containerId, maxFiles) {{
        const container = document.getElementById(containerId);
        container.innerHTML = '';
        
        if (input.files.length > maxFiles) {{
            alert(`Максимальное количество файлов: ${maxFiles}`);
            input.value = '';
            return;
        }}
        
        for (let i = 0; i < input.files.length; i++) {{
            const file = input.files[i];
            const reader = new FileReader();
            
            reader.onload = function(e) {{
                const div = document.createElement('div');
                div.className = 'media-item';
                
                if (file.type.startsWith('image/')) {{
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    div.appendChild(img);
                }} else if (file.type.startsWith('video/')) {{
                    const video = document.createElement('video');
                    video.src = e.target.result;
                    video.controls = true;
                    div.appendChild(video);
                }}
                
                const removeBtn = document.createElement('button');
                removeBtn.className = 'remove-media';
                removeBtn.innerHTML = '×';
                removeBtn.onclick = function() {{
                    container.removeChild(div);
                    // Обновить input files
                    const dt = new DataTransfer();
                    for (let j = 0; j < input.files.length; j++) {{
                        if (j !== i) dt.items.add(input.files[j]);
                    }}
                    input.files = dt.files;
                }};
                div.appendChild(removeBtn);
                container.appendChild(div);
            }}
            
            reader.readAsDataURL(file);
        }}
    }}
    </script>
</body>
</html>'''

def get_flash_html():
    html = ""
    for category, message in get_flashed_messages(with_categories=True):
        if category == 'success':
            html += f'<div class="alert alert-success">{message}</div>'
        elif category == 'error':
            html += f'<div class="alert alert-error">{message}</div>'
        elif category == 'warning':
            html += f'<div class="alert alert-warning">{message}</div>'
        else:
            html += f'<div class="alert alert-info">{message}</div>'
    return html

def render_page(title, content):
    return render_template_string(
        BASE_HTML.format(
            title=title,
            flash_messages=get_flash_html(),
            content=content
        )
    )

# ========== МАРШРУТЫ ==========
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect('/feed')
    
    content = '''<div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">Добро пожаловать в MateuGram!</h2>
        <p style="margin-bottom: 25px; line-height: 1.6;">
            Безопасная социальная сеть без политики, религии и нецензурной лексики. 
            Общайтесь с друзьями, делитесь моментами и находите единомышленников.
        </p>
        
        <div style="display: flex; gap: 15px; margin-top: 30px;">
            <a href="/register" class="btn">📝 Зарегистрироваться</a>
            <a href="/login" class="btn btn-secondary">🔑 Войти</a>
        </div>
    </div>'''
    
    return render_page('Главная', content)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        password = request.form['password']
        
        if not validate_username(username):
            flash('Псевдоним должен содержать только английские буквы, цифры и символы _ . -', 'error')
            return redirect('/register')
        
        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'error')
            return redirect('/register')
        
        if User.query.filter_by(username=username).first():
            flash('Псевдоним уже занят', 'error')
            return redirect('/register')
        
        is_admin = (username.lower() == 'mateugram')
        
        new_user = User(
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            password_hash=generate_password_hash(password),
            email_verified=True,
            verification_code=None,
            is_active=True,
            is_admin=is_admin
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user, remember=True)
        
        if is_admin:
            flash(f'✅ Регистрация успешна! Вы зарегистрированы как администратор.', 'success')
        else:
            flash(f'✅ Регистрация успешна! Добро пожаловать, {first_name}!', 'success')
        
        return redirect('/feed')
    
    content = '''<div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">Регистрация в MateuGram</h2>
        
        <form method="POST" action="/register">
            <div class="form-group">
                <label class="form-label">📧 Email</label>
                <input type="email" name="email" class="form-input" placeholder="example@mail.com" required>
            </div>
            
            <div class="form-group">
                <label class="form-label">👤 Псевдоним (только английские буквы)</label>
                <input type="text" name="username" class="form-input" placeholder="john_doe" required>
                <small style="color: #666; display: block; margin-top: 5px;">
                    Разрешены: буквы a-z, цифры 0-9, символы _ . -
                </small>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                <div class="form-group">
                    <label class="form-label">👤 Имя</label>
                    <input type="text" name="first_name" class="form-input" placeholder="Иван" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">👤 Фамилия</label>
                    <input type="text" name="last_name" class="form-input" placeholder="Иванов" required>
                </div>
            </div>
            
            <div class="form-group">
                <label class="form-label">🔒 Пароль</label>
                <input type="password" name="password" class="form-input" placeholder="Не менее 8 символов" required minlength="8">
            </div>
            
            <button type="submit" class="btn">📝 Создать аккаунт</button>
        </form>
        
        <div style="text-align: center; margin-top: 20px;">
            <p>Уже есть аккаунт? <a href="/login" style="color: #2a5298;">Войти</a></p>
        </div>
    </div>'''
    
    return render_page('Регистрация', content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']
        password = request.form['password']
        
        user = User.query.filter(
            (User.email == identifier) | (User.username == identifier)
        ).first()
        
        if user and check_password_hash(user.password_hash, password):
            if user.is_banned:
                flash('❌ Ваш аккаунт заблокирован администратором', 'error')
                return redirect('/login')
            
            login_user(user, remember=True)
            
            if user.is_admin:
                flash(f'👑 Добро пожаловать, администратор {user.first_name}!', 'success')
            else:
                flash(f'Добро пожаловать, {user.first_name}!', 'success')
            
            return redirect('/feed')
        else:
            flash('Неверные email/пароль или псевдоним', 'error')
    
    content = '''<div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">Вход в MateuGram</h2>
        
        <form method="POST" action="/login">
            <div class="form-group">
                <label class="form-label">📧 Email или псевдоним</label>
                <input type="text" name="identifier" class="form-input" placeholder="example@mail.com или john_doe" required>
            </div>
            
            <div class="form-group">
                <label class="form-label">🔒 Пароль</label>
                <input type="password" name="password" class="form-input" placeholder="Ваш пароль" required>
            </div>
            
            <button type="submit" class="btn">🔑 Войти</button>
        </form>
        
        <div style="text-align: center; margin-top: 20px;">
            <p>Нет аккаунта? <a href="/register" style="color: #2a5298;">Зарегистрироваться</a></p>
        </div>
    </div>'''
    
    return render_page('Вход', content)

# ========== РЕДАКТИРОВАНИЕ ПРОФИЛЯ ==========
@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        user = User.query.get(current_user.id)
        
        # Обновляем основные данные
        user.first_name = request.form.get('first_name', user.first_name)
        user.last_name = request.form.get('last_name', user.last_name)
        user.username = request.form.get('username', user.username)
        user.email = request.form.get('email', user.email)
        user.bio = request.form.get('bio', user.bio)
        
        # Проверяем уникальность username
        if user.username != current_user.username:
            existing_user = User.query.filter_by(username=user.username).first()
            if existing_user and existing_user.id != current_user.id:
                flash('❌ Этот псевдоним уже занят', 'error')
                return redirect('/edit_profile')
        
        # Проверяем уникальность email
        if user.email != current_user.email:
            existing_user = User.query.filter_by(email=user.email).first()
            if existing_user and existing_user.id != current_user.id:
                flash('❌ Этот email уже занят', 'error')
                return redirect('/edit_profile')
        
        # Обновляем пароль, если указан новый
        new_password = request.form.get('new_password')
        if new_password and new_password.strip():
            if len(new_password) < 8:
                flash('❌ Пароль должен содержать минимум 8 символов', 'error')
                return redirect('/edit_profile')
            user.password_hash = generate_password_hash(new_password)
            flash('✅ Пароль успешно изменен', 'success')
        
        # Обновляем аватар
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file.filename:
                saved_name = save_file(file, 'image')
                if saved_name:
                    user.avatar_filename = saved_name
                    flash('✅ Аватар обновлен', 'success')
        
        db.session.commit()
        flash('✅ Профиль успешно обновлен', 'success')
        return redirect(f'/profile/{user.id}')
    
    content = f'''<div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">Редактирование профиля</h2>
        
        <form method="POST" action="/edit_profile" enctype="multipart/form-data">
            <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 30px;">
                <div>
                    <img src="/static/uploads/{current_user.avatar_filename}" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 3px solid #2a5298;">
                </div>
                <div>
                    <label class="form-label">Аватар</label>
                    <input type="file" name="avatar" accept="image/*">
                    <small style="color: #666;">Максимальный размер: 2MB</small>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                <div class="form-group">
                    <label class="form-label">👤 Имя</label>
                    <input type="text" name="first_name" class="form-input" value="{current_user.first_name}" required>
                </div>
                
                <div class="form-group">
                    <label class="form-label">👤 Фамилия</label>
                    <input type="text" name="last_name" class="form-input" value="{current_user.last_name}" required>
                </div>
            </div>
            
            <div class="form-group">
                <label class="form-label">👤 Псевдоним</label>
                <input type="text" name="username" class="form-input" value="{current_user.username}" required>
            </div>
            
            <div class="form-group">
                <label class="form-label">📧 Email</label>
                <input type="email" name="email" class="form-input" value="{current_user.email}" required>
            </div>
            
            <div class="form-group">
                <label class="form-label">📝 О себе</label>
                <textarea name="bio" class="form-input" rows="4" placeholder="Расскажите о себе...">{current_user.bio}</textarea>
            </div>
            
            <div class="form-group">
                <label class="form-label">🔒 Новый пароль (оставьте пустым, если не хотите менять)</label>
                <input type="password" name="new_password" class="form-input" placeholder="Новый пароль (мин. 8 символов)">
            </div>
            
            <div style="display: flex; gap: 10px; margin-top: 30px;">
                <button type="submit" class="btn">💾 Сохранить изменения</button>
                <a href="/profile/{current_user.id}" class="btn btn-secondary">❌ Отмена</a>
            </div>
        </form>
    </div>'''
    
    return render_page('Редактирование профиля', content)

# ========== СОЗДАНИЕ ПОСТОВ С МЕДИА ==========
@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        content = request.form['content']
        post_type = request.form.get('post_type', 'text')
        
        if not content.strip() and 'images' not in request.files and 'videos' not in request.files:
            flash('❌ Пост должен содержать текст или медиафайлы', 'error')
            return redirect('/create_post')
        
        is_clean, found_words = check_content_for_report(content)
        if not is_clean:
            flash(f'⚠️ В вашем посте обнаружены слова, на которые могут пожаловаться: {", ".join(found_words)}', 'warning')
        
        # Сохраняем изображения (до 10)
        images = []
        if 'images' in request.files:
            image_files = request.files.getlist('images')
            images = save_media_files(image_files, 10, 'image')
        
        # Сохраняем видео (до 5)
        videos = []
        if 'videos' in request.files:
            video_files = request.files.getlist('videos')
            videos = save_media_files(video_files, 5, 'video')
        
        import json
        new_post = Post(
            content=content,
            post_type=post_type,
            user_id=current_user.id,
            images=json.dumps(images),
            videos=json.dumps(videos)
        )
        
        db.session.add(new_post)
        db.session.commit()
        
        flash('✅ Пост опубликован', 'success')
        return redirect('/feed')
    
    content = f'''<div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">Создать пост</h2>
        
        <form method="POST" action="/create_post" enctype="multipart/form-data">
            <div class="form-group">
                <label class="form-label">💬 Текст поста</label>
                <textarea name="content" id="post-content" class="form-input" rows="5" placeholder="Что у вас нового?"></textarea>
                
                <button type="button" class="btn btn-small" onclick="toggleEmojiPicker('post-content')" style="margin-top: 10px;">😊 Добавить смайлик</button>
                
                <div id="post-content-picker" class="emoji-picker" style="display: none;">
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '😊')">😊</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '😂')">😂</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '❤️')">❤️</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '👍')">👍</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '🔥')">🔥</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '🎉')">🎉</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '😍')">😍</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '😎')">😎</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '🙏')">🙏</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('post-content', '💯')">💯</button>
                </div>
            </div>
            
            <div class="form-group">
                <label class="form-label">🖼️ Фотографии (до 10)</label>
                <input type="file" name="images" accept="image/*" multiple onchange="previewMedia(this, 'image-preview', 10)">
                <div id="image-preview" class="media-preview"></div>
                <small style="color: #666;">Поддерживаемые форматы: PNG, JPG, JPEG, GIF</small>
            </div>
            
            <div class="form-group">
                <label class="form-label">🎬 Видео (до 5)</label>
                <input type="file" name="videos" accept="video/*" multiple onchange="previewMedia(this, 'video-preview', 5)">
                <div id="video-preview" class="media-preview"></div>
                <small style="color: #666;">Поддерживаемые форматы: MP4, MOV, AVI, MKV</small>
            </div>
            
            <input type="hidden" name="post_type" value="media">
            
            <div style="display: flex; gap: 10px; margin-top: 30px;">
                <button type="submit" class="btn">📤 Опубликовать</button>
                <a href="/feed" class="btn btn-secondary">❌ Отмена</a>
            </div>
        </form>
    </div>'''
    
    return render_page('Создать пост', content)

# ========== ЛЕНТА С МЕДИА ==========
@app.route('/feed')
@login_required
def feed():
    # Получаем посты, исключая заблокированных пользователей
    blocked_ids = [b.blocked_id for b in BlockedUser.query.filter_by(blocker_id=current_user.id).all()]
    
    posts = Post.query.filter(
        Post.is_hidden == False,
        ~Post.user_id.in_(blocked_ids)
    ).order_by(Post.created_at.desc()).all()
    
    posts_html = ""
    for post in posts:
        import json
        images = json.loads(post.images) if post.images else []
        videos = json.loads(post.videos) if post.videos else []
        
        media_html = ""
        if images or videos:
            media_html = '<div class="media-gallery">'
            for img in images:
                media_html += f'''<div class="gallery-item">
                    <img src="/static/uploads/{img}" onclick="this.style.transform = this.style.transform === 'scale(1.5)' ? 'scale(1)' : 'scale(1.5)'; this.style.zIndex = this.style.zIndex === '100' ? '1' : '100';" style="cursor: pointer; transition: transform 0.3s; position: relative;">
                </div>'''
            for vid in videos:
                media_html += f'''<div class="gallery-item">
                    <video src="/static/uploads/{vid}" controls style="cursor: pointer;"></video>
                </div>'''
            media_html += '</div>'
        
        posts_html += f'''<div class="post">
            <div class="post-header">
                <img src="/static/uploads/{post.author.avatar_filename}" class="avatar">
                <div>
                    <div class="post-author">{post.author.first_name} {post.author.last_name}</div>
                    <small>@{post.author.username}</small>
                </div>
                <div class="post-time">{post.created_at.strftime('%d.%m.%Y %H:%M')}</div>
            </div>
            
            <div class="post-content">{get_emoji_html(post.content)}</div>
            
            {media_html}
            
            <div class="post-stats">
                <span>❤️ {get_like_count(post.id)}</span>
                <span>💬 {get_comment_count(post.id)}</span>
            </div>
            
            <div class="post-actions">
                <a href="/like_post/{post.id}" class="btn btn-small btn-like">❤️ Нравится</a>
                <button onclick="document.getElementById('comment-form-{post.id}').style.display='block'" class="btn btn-small btn-comment">💬 Комментировать</button>
                <button onclick="confirmReport('post', {post.id})" class="btn btn-small btn-report">🚫 Пожаловаться</button>
            </div>
            
            <div id="comment-form-{post.id}" style="display: none; margin-top: 15px;">
                <form method="POST" action="/add_comment/{post.id}">
                    <textarea name="content" id="comment-{post.id}" class="comment-input" placeholder="Добавить комментарий..."></textarea>
                    <button type="button" class="btn btn-small" onclick="toggleEmojiPicker('comment-{post.id}')" style="margin-top: 5px;">😊 Смайлик</button>
                    <button type="submit" class="btn btn-small" style="margin-top: 5px;">Отправить</button>
                    
                    <div id="comment-{post.id}-picker" class="emoji-picker" style="display: none;">
                        <button type="button" class="emoji-btn" onclick="insertEmoji('comment-{post.id}', '😊')">😊</button>
                        <button type="button" class="emoji-btn" onclick="insertEmoji('comment-{post.id}', '😂')">😂</button>
                        <button type="button" class="emoji-btn" onclick="insertEmoji('comment-{post.id}', '👍')">👍</button>
                        <button type="button" class="emoji-btn" onclick="insertEmoji('comment-{post.id}', '❤️')">❤️</button>
                    </div>
                </form>
            </div>
        </div>'''
    
    content = f'''<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2 style="color: #2a5298;">📰 Лента новостей</h2>
        <div>
            <a href="/create_post" class="btn">📝 Создать пост</a>
            <a href="/edit_profile" class="btn btn-secondary" style="margin-left: 10px;">👤 Профиль</a>
        </div>
    </div>
    
    {posts_html if posts_html else '<div class="card"><p style="text-align: center; color: #666; padding: 40px;">Лента пуста. Будьте первым, кто опубликует пост!</p></div>'}'''
    
    return render_page('Лента', content)

# ========== ЛИЧНЫЕ СООБЩЕНИЯ С ЭМОДЗИ ==========
@app.route('/messages/<int:receiver_id>', methods=['GET', 'POST'])
@login_required
def messages(receiver_id):
    receiver = User.query.get_or_404(receiver_id)
    
    if request.method == 'POST':
        content = request.form['content']
        
        if not content.strip():
            flash('❌ Сообщение не может быть пустым', 'error')
            return redirect(f'/messages/{receiver_id}')
        
        is_clean, found_words = check_content_for_report(content)
        if not is_clean:
            flash(f'⚠️ В вашем сообщении обнаружены слова, на которые могут пожаловаться: {", ".join(found_words)}', 'warning')
        
        new_message = Message(
            content=content,
            sender_id=current_user.id,
            receiver_id=receiver_id
        )
        
        db.session.add(new_message)
        db.session.commit()
        
        return redirect(f'/messages/{receiver_id}')
    
    # Получаем историю сообщений
    messages_history = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == receiver_id)) |
        ((Message.sender_id == receiver_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at).all()
    
    messages_html = ""
    for msg in messages_history:
        message_class = "sent" if msg.sender_id == current_user.id else "received"
        messages_html += f'''<div class="message {message_class}">
            <div class="message-header">
                <span>{msg.sender.first_name} {msg.sender.last_name}</span>
                <span>{msg.created_at.strftime('%H:%M')}</span>
            </div>
            <div class="message-content">{get_emoji_html(msg.content)}</div>
        </div>'''
    
    content = f'''<div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">💬 Диалог с {receiver.first_name} {receiver.last_name}</h2>
        
        <div style="max-height: 400px; overflow-y: auto; margin-bottom: 20px;">
            {messages_html if messages_html else '<p style="text-align: center; color: #666; padding: 20px;">Нет сообщений. Начните диалог!</p>'}
        </div>
        
        <form method="POST" action="/messages/{receiver_id}">
            <div class="form-group">
                <textarea name="content" id="message-content" class="form-input" rows="3" placeholder="Введите сообщение..."></textarea>
                
                <button type="button" class="btn btn-small" onclick="toggleEmojiPicker('message-content')" style="margin-top: 10px;">😊 Добавить смайлик</button>
                
                <div id="message-content-picker" class="emoji-picker" style="display: none;">
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '😊')">😊</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '😂')">😂</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '❤️')">❤️</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '👍')">👍</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '🙏')">🙏</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '🎉')">🎉</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '😉')">😉</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '😎')">😎</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '🤔')">🤔</button>
                    <button type="button" class="emoji-btn" onclick="insertEmoji('message-content', '🔥')">🔥</button>
                </div>
            </div>
            
            <button type="submit" class="btn">📤 Отправить</button>
            <a href="/messages" class="btn btn-secondary" style="margin-left: 10px;">← Назад</a>
        </form>
    </div>'''
    
    return render_page('Сообщения', content)

# ========== ОСНОВНЫЕ МАРШРУТЫ (без изменений) ==========
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('✅ Вы вышли из системы', 'success')
    return redirect('/')

@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)
    
    if is_user_blocked(current_user.id, user_id):
        return render_page('Профиль', '<div class="card"><p style="text-align: center; color: #666; padding: 40px;">🚫 Вы заблокировали этого пользователя</p></div>')
    
    posts_count = Post.query.filter_by(user_id=user_id).count()
    
    content = f'''<div class="profile-header">
        <img src="/static/uploads/{user.avatar_filename}" class="profile-avatar">
        <div class="profile-info">
            <h2>{user.first_name} {user.last_name}</h2>
            <p>@{user.username}</p>
            <p>📧 {user.email}</p>
            <p>📅 Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}</p>
            <p>📝 Постов: {posts_count}</p>
            {f'<div class="admin-label">👑 Администратор</div>' if user.is_admin else ''}
            {f'<div class="banned-label">🚫 Забанен</div>' if user.is_banned else ''}
        </div>
    </div>
    
    <div class="card">
        <h3 style="color: #2a5298; margin-bottom: 15px;">📝 О себе</h3>
        {f'<div class="bio-text">{get_emoji_html(user.bio)}</div>' if user.bio else '<p style="color: #666; text-align: center;">Пользователь не добавил информацию о себе.</p>'}
    </div>
    
    <div style="display: flex; gap: 10px; margin-top: 20px;">
        {f'<a href="/edit_profile" class="btn">✏️ Редактировать профиль</a>' if user_id == current_user.id else ''}
        {f'<a href="/messages/{user_id}" class="btn">💬 Написать сообщение</a>' if user_id != current_user.id else ''}
        {f'<button onclick="confirmBlock({user_id}, \'{user.username}\')" class="btn btn-block">🚫 Заблокировать</button>' if user_id != current_user.id else ''}
    </div>'''
    
    return render_page(f'Профиль {user.username}', content)

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Создаем дефолтный аватар если нужно
        default_avatar_path = os.path.join('static', 'uploads', 'default_avatar.png')
        if not os.path.exists(default_avatar_path):
            # Создаем простой PNG аватар
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (200, 200), color=(42, 82, 152))
            d = ImageDraw.Draw(img)
            d.ellipse([50, 50, 150, 150], fill=(255, 255, 255))
            img.save(default_avatar_path)
        
        print("✅ База данных создана")
    
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=False)
