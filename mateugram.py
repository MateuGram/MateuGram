"""
MateuGram - Синяя социальная сеть
ПОЛНАЯ ВЕРСИЯ С ИСПРАВЛЕНИЯМИ
"""

import os
import json
import shutil
from datetime import datetime, date
from flask import Flask, request, redirect, url_for, flash, get_flashed_messages, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import re
import secrets
import atexit

# ========== НАСТРОЙКА ПРИЛОЖЕНИЯ ==========
app = Flask(__name__)

# Генерируем SECRET_KEY для сессий
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ========== БАЗА ДАННЫХ ==========
# Важная настройка для сохранения данных на Render.com
if 'RENDER' in os.environ:
    print("🌐 Обнаружен Render.com - использую постоянное хранилище...")
    # Используем папку /tmp которая сохраняется между деплоями
    DB_FILE = '/tmp/mateugram_persistent.db'
    BACKUP_DIR = '/tmp/backups'
    os.makedirs(BACKUP_DIR, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_FILE}'
    print(f"📁 База данных: {DB_FILE}")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mateugram.db'
    BACKUP_DIR = 'backups'
    os.makedirs(BACKUP_DIR, exist_ok=True)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Создаем папки если их нет
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    bio = db.Column(db.Text, default='')
    avatar_filename = db.Column(db.String(200), default='')
    birthday = db.Column(db.Date, nullable=True)
    
    # Связи
    posts = db.relationship('Post', backref='author', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy=True, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    following = db.relationship('Follow', foreign_keys='Follow.follower_id', backref='follower', lazy=True)
    followers = db.relationship('Follow', foreign_keys='Follow.followed_id', backref='followed', lazy=True)

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_hidden = db.Column(db.Boolean, default=False)
    views_count = db.Column(db.Integer, default=0)
    images = db.Column(db.Text, default='')
    
    # Связи
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy=True, cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except:
        return None

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def validate_username(username):
    pattern = r'^[a-zA-Z0-9_.-]+$'
    return bool(re.match(pattern, username))

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_file(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{secrets.token_hex(8)}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        try:
            file.save(filepath)
            return unique_filename
        except:
            return None
    return None

def get_emoji_html(content):
    emoji_map = {
        ':)': '😊', ':(': '😔', ':D': '😃', ':P': '😛', ';)': '😉',
        ':/': '😕', ':O': '😮', ':*': '😘', '<3': '❤️', '</3': '💔'
    }
    for code, emoji in emoji_map.items():
        content = content.replace(code, emoji)
    return content

def is_following(follower_id, followed_id):
    return Follow.query.filter_by(follower_id=follower_id, followed_id=followed_id).first() is not None

def get_following_count(user_id):
    return Follow.query.filter_by(follower_id=user_id).count()

def get_followers_count(user_id):
    return Follow.query.filter_by(followed_id=user_id).count()

def get_like_count(post_id):
    return Like.query.filter_by(post_id=post_id).count()

def get_comment_count(post_id):
    return Comment.query.filter_by(post_id=post_id).count()

def get_unread_messages_count(user_id):
    return Message.query.filter_by(receiver_id=user_id, is_read=False).count()

def user_has_liked(user_id, post_id):
    return Like.query.filter_by(user_id=user_id, post_id=post_id).first() is not None

def create_backup():
    """Создание резервной копии базы данных"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if 'RENDER' in os.environ:
            db_path = '/tmp/mateugram_persistent.db'
            backup_path = f'/tmp/backups/mateugram_backup_{timestamp}.db'
        else:
            db_path = 'mateugram.db'
            backup_path = f'backups/mateugram_backup_{timestamp}.db'
        
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
            
            # Удаляем старые бэкапы (оставляем последние 10)
            backup_files = []
            if os.path.exists(BACKUP_DIR):
                backup_files = sorted(
                    [f for f in os.listdir(BACKUP_DIR) if f.startswith('mateugram_backup_')],
                    reverse=True
                )
                
                for old_backup in backup_files[10:]:
                    os.remove(os.path.join(BACKUP_DIR, old_backup))
            
            print(f"✅ Резервная копия создана: {backup_path}")
            return True
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")
    return False

def get_avatar_url(user):
    """Получение URL аватара пользователя"""
    if user.avatar_filename and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], user.avatar_filename)):
        return f"/static/uploads/{user.avatar_filename}"
    return None

# ========== HTML ШАБЛОНЫ ==========
BASE_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MateuGram - {title}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: linear-gradient(135deg, #1a2980, #26d0ce); color: #333; min-height: 100vh; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        
        .header { 
            background: rgba(255, 255, 255, 0.95); 
            border-radius: 20px; 
            padding: 30px; 
            margin-bottom: 25px; 
            text-align: center; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.1); 
            border: 1px solid rgba(255, 255, 255, 0.3);
        }
        .header h1 { 
            color: #2a5298; 
            margin-bottom: 15px; 
            font-size: 3em; 
            font-weight: 800; 
            background: linear-gradient(45deg, #1a2980, #26d0ce); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent; 
            text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        }
        .header p { color: #666; font-size: 1.2em; font-weight: 300; }
        
        .card { 
            background: rgba(255, 255, 255, 0.95); 
            border-radius: 20px; 
            padding: 30px; 
            margin-bottom: 25px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.1); 
            border: 1px solid rgba(255, 255, 255, 0.3);
            transition: transform 0.3s ease;
        }
        .card:hover { transform: translateY(-5px); }
        
        .form-group { margin-bottom: 25px; }
        .form-input { 
            width: 100%; 
            padding: 15px 20px; 
            border: 2px solid #e1e8ed; 
            border-radius: 12px; 
            font-size: 16px; 
            transition: all 0.3s ease; 
            background: rgba(255, 255, 255, 0.9); 
        }
        .form-input:focus { 
            outline: none; 
            border-color: #2a5298; 
            box-shadow: 0 0 0 3px rgba(42,82,152,0.1); 
        }
        
        .btn { 
            background: linear-gradient(45deg, #2a5298, #1e3c72); 
            color: white; 
            border: none; 
            padding: 15px 30px; 
            border-radius: 12px; 
            cursor: pointer; 
            text-decoration: none; 
            display: inline-block; 
            font-weight: 600; 
            font-size: 16px; 
            transition: all 0.3s ease; 
            box-shadow: 0 5px 15px rgba(42,82,152,0.2);
        }
        .btn:hover { 
            transform: translateY(-2px); 
            box-shadow: 0 8px 20px rgba(42,82,152,0.3); 
            background: linear-gradient(45deg, #1e3c72, #162b5f);
        }
        .btn-danger { 
            background: linear-gradient(45deg, #dc3545, #c82333); 
            box-shadow: 0 5px 15px rgba(220,53,69,0.2);
        }
        .btn-danger:hover { 
            background: linear-gradient(45deg, #c82333, #bd2130); 
            box-shadow: 0 8px 20px rgba(220,53,69,0.3);
        }
        .btn-success { 
            background: linear-gradient(45deg, #28a745, #1e7e34); 
            box-shadow: 0 5px 15px rgba(40,167,69,0.2);
        }
        .btn-success:hover { 
            background: linear-gradient(45deg, #1e7e34, #186429); 
            box-shadow: 0 8px 20px rgba(40,167,69,0.3);
        }
        .btn-warning { 
            background: linear-gradient(45deg, #ffc107, #e0a800); 
            color: #000; 
            box-shadow: 0 5px 15px rgba(255,193,7,0.2);
        }
        .btn-admin { 
            background: linear-gradient(45deg, #6f42c1, #5a32a3); 
            box-shadow: 0 5px 15px rgba(111,66,193,0.2);
        }
        
        .nav { display: flex; gap: 15px; margin-bottom: 30px; flex-wrap: wrap; justify-content: center; }
        .nav-btn { 
            background: rgba(255,255,255,0.9); 
            color: #2a5298; 
            border: 2px solid #2a5298; 
            padding: 12px 25px; 
            border-radius: 12px; 
            text-decoration: none; 
            font-weight: 600; 
            transition: all 0.3s ease; 
            display: flex; 
            align-items: center; 
            gap: 8px; 
        }
        .nav-btn:hover { 
            background: #2a5298; 
            color: white; 
            transform: translateY(-2px); 
            box-shadow: 0 5px 15px rgba(42,82,152,0.2);
        }
        
        .post { 
            background: rgba(255,255,255,0.95); 
            border-radius: 18px; 
            padding: 25px; 
            margin-bottom: 20px; 
            box-shadow: 0 8px 25px rgba(0,0,0,0.08); 
            border: 1px solid rgba(255,255,255,0.3);
            transition: transform 0.3s ease;
        }
        .post:hover { transform: translateY(-3px); }
        
        .post-header { display: flex; align-items: center; margin-bottom: 20px; }
        .avatar { 
            width: 60px; 
            height: 60px; 
            border-radius: 50%; 
            background: linear-gradient(45deg, #2a5298, #1e3c72); 
            color: white; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            font-weight: bold; 
            font-size: 1.3em; 
            margin-right: 15px; 
            box-shadow: 0 5px 15px rgba(42,82,152,0.2); 
            background-size: cover;
            background-position: center;
        }
        
        .alert { 
            padding: 20px; 
            border-radius: 15px; 
            margin-bottom: 25px; 
            font-weight: 500; 
            animation: slideIn 0.5s ease;
        }
        @keyframes slideIn {
            from { transform: translateY(-20px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        .alert-success { background: linear-gradient(45deg, #d4edda, #c3e6cb); color: #155724; border-left: 5px solid #28a745; }
        .alert-error { background: linear-gradient(45deg, #f8d7da, #f5c6cb); color: #721c24; border-left: 5px solid #dc3545; }
        .alert-info { background: linear-gradient(45deg, #d1ecf1, #bee5eb); color: #0c5460; border-left: 5px solid #17a2b8; }
        
        .user-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; margin-top: 25px; }
        .user-card { 
            background: rgba(255,255,255,0.95); 
            border-radius: 18px; 
            padding: 20px; 
            transition: all 0.3s ease; 
            border: 1px solid rgba(255,255,255,0.3);
        }
        .user-card:hover { transform: translateY(-5px); box-shadow: 0 15px 35px rgba(0,0,0,0.1); }
        
        .admin-badge { 
            background: linear-gradient(45deg, #6f42c1, #5a32a3); 
            color: white; 
            padding: 5px 12px; 
            border-radius: 20px; 
            font-size: 12px; 
            font-weight: bold; 
            margin-left: 8px; 
            display: inline-block; 
        }
        
        .follow-stats { display: flex; gap: 25px; margin: 20px 0; justify-content: center; }
        .follow-stat { 
            text-align: center; 
            padding: 20px; 
            background: rgba(255,255,255,0.9); 
            border-radius: 15px; 
            min-width: 120px; 
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
        }
        .follow-stat-number { font-size: 2em; font-weight: 800; color: #2a5298; margin-bottom: 5px; }
        
        .post-actions { display: flex; gap: 12px; margin-top: 20px; flex-wrap: wrap; }
        .btn-small { padding: 10px 18px; font-size: 14px; border-radius: 10px; }
        
        .media-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 15px; margin: 20px 0; }
        .media-item { 
            border-radius: 12px; 
            overflow: hidden; 
            box-shadow: 0 5px 15px rgba(0,0,0,0.1); 
            transition: transform 0.3s ease;
        }
        .media-item:hover { transform: scale(1.03); }
        .media-item img { width: 100%; height: 180px; object-fit: cover; }
        
        .info-box { 
            background: linear-gradient(135deg, rgba(248,249,250,0.9), rgba(233,236,239,0.9)); 
            padding: 25px; 
            border-radius: 18px; 
            margin: 25px 0; 
            border-left: 6px solid #2a5298; 
            box-shadow: 0 8px 25px rgba(0,0,0,0.05);
        }
        
        h2, h3, h4 { color: #2a5298; margin-bottom: 20px; font-weight: 700; }
        h2 { 
            font-size: 2.2em; 
            background: linear-gradient(45deg, #1a2980, #26d0ce); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent;
        }
        
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; margin: 25px 0; }
        .stat-item { 
            background: rgba(255,255,255,0.9); 
            border-radius: 15px; 
            padding: 25px; 
            text-align: center; 
            box-shadow: 0 8px 25px rgba(0,0,0,0.05);
            transition: transform 0.3s ease;
        }
        .stat-item:hover { transform: translateY(-5px); }
        .stat-number { font-size: 2.5em; font-weight: 800; color: #2a5298; margin-bottom: 10px; }
        
        table { 
            width: 100%; 
            border-collapse: separate; 
            border-spacing: 0; 
            background: rgba(255,255,255,0.9); 
            border-radius: 15px; 
            overflow: hidden; 
            box-shadow: 0 8px 25px rgba(0,0,0,0.05);
        }
        th { 
            background: linear-gradient(45deg, #2a5298, #1e3c72); 
            color: white; 
            padding: 18px; 
            text-align: left; 
            font-weight: 600;
        }
        td { padding: 16px; border-bottom: 1px solid #e1e8ed; }
        tr:hover { background: rgba(248,249,250,0.8); }
        
        @media (max-width: 768px) {
            .container { padding: 10px; }
            .header h1 { font-size: 2.2em; }
            .nav { flex-direction: column; }
            .user-list { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-comments"></i> MateuGram</h1>
            <p>Синяя социальная сеть для безопасного общения</p>
        </div>
        
        <div class="nav">
            <a href="/" class="nav-btn"><i class="fas fa-home"></i> Главная</a>
            {nav_links}
        </div>
        
        {flash_messages}
        
        {content}
    </div>
    
    <script>
    function confirmAction(message, url) {
        if (confirm(message)) {
            window.location.href = url;
        }
    }
    
    function toggleComments(postId) {
        const commentsDiv = document.getElementById('comments-' + postId);
        if (commentsDiv.style.display === 'none') {
            commentsDiv.style.display = 'block';
        } else {
            commentsDiv.style.display = 'none';
        }
    }
    </script>
</body>
</html>'''

def render_page(title, content):
    nav_links = ''
    if current_user.is_authenticated:
        unread_count = get_unread_messages_count(current_user.id)
        messages_badge = f' <span style="background: #dc3545; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em;">{unread_count}</span>' if unread_count > 0 else ''
        
        nav_links = f'''
            <a href="/feed" class="nav-btn"><i class="fas fa-newspaper"></i> Лента</a>
            <a href="/create_post" class="nav-btn"><i class="fas fa-edit"></i> Создать пост</a>
            <a href="/profile/{current_user.id}" class="nav-btn"><i class="fas fa-user"></i> Мой профиль</a>
            <a href="/users" class="nav-btn"><i class="fas fa-users"></i> Пользователи</a>
            <a href="/messages" class="nav-btn"><i class="fas fa-envelope"></i> Сообщения{messages_badge}</a>
        '''
        if current_user.is_admin:
            nav_links += '<a href="/admin" class="nav-btn btn-admin"><i class="fas fa-crown"></i> Админ</a>'
        nav_links += '<a href="/logout" class="nav-btn btn-danger"><i class="fas fa-sign-out-alt"></i> Выйти</a>'
    else:
        nav_links = '''
            <a href="/login" class="nav-btn"><i class="fas fa-key"></i> Вход</a>
            <a href="/register" class="nav-btn"><i class="fas fa-user-plus"></i> Регистрация</a>
        '''
    
    flash_messages = ''
    messages = get_flashed_messages(with_categories=True)
    for category, message in messages:
        if category == 'success':
            flash_class = 'alert-success'
        elif category == 'error' or category == 'danger':
            flash_class = 'alert-error'
        else:
            flash_class = 'alert-info'
        flash_messages += f'<div class="alert {flash_class}">{message}</div>'
    
    html = BASE_HTML.replace('{title}', title)
    html = html.replace('{nav_links}', nav_links)
    html = html.replace('{flash_messages}', flash_messages)
    html = html.replace('{content}', content)
    
    return html

# ========== ОСНОВНЫЕ МАРШРУТЫ ==========
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect('/feed')
    
    with app.app_context():
        try:
            total_users = User.query.count()
            total_posts = Post.query.count()
            total_comments = Comment.query.count()
        except:
            total_users = 0
            total_posts = 0
            total_comments = 0
    
    return render_page('Главная', f'''
    <div class="card">
        <h2><i class="fas fa-hand-wave"></i> Добро пожаловать в MateuGram!</h2>
        <p style="margin-bottom: 25px; line-height: 1.8; font-size: 1.1em;">
            Безопасная социальная сеть без политики, религии и нецензурной лексики. 
            Общайтесь с друзьями, делитесь моментами и находите единомышленников в уютной атмосфере.
        </p>
        
        <div class="info-box">
            <h3><i class="fas fa-chart-bar"></i> Статистика сети</h3>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-number">{total_users}</div>
                    <div class="stat-label"><i class="fas fa-users"></i> Пользователей</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{total_posts}</div>
                    <div class="stat-label"><i class="fas fa-newspaper"></i> Постов</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{total_comments}</div>
                    <div class="stat-label"><i class="fas fa-comments"></i> Комментариев</div>
                </div>
            </div>
        </div>
        
        <div style="display: flex; gap: 20px; margin-top: 30px; justify-content: center;">
            <a href="/register" class="btn" style="padding: 18px 40px; font-size: 18px;">
                <i class="fas fa-user-plus"></i> Зарегистрироваться
            </a>
            <a href="/login" class="btn btn-success" style="padding: 18px 40px; font-size: 18px;">
                <i class="fas fa-key"></i> Войти
            </a>
        </div>
    </div>
    
    <div class="card">
        <h3><i class="fas fa-star"></i> Возможности MateuGram</h3>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 25px; margin-top: 20px;">
            <div style="background: rgba(248, 249, 250, 0.8); padding: 25px; border-radius: 15px; border-left: 5px solid #2a5298;">
                <h4 style="color: #2a5298; margin-bottom: 15px;"><i class="fas fa-pen-alt"></i> Создание контента</h4>
                <ul style="list-style: none; padding: 0;">
                    <li style="padding: 10px 0; border-bottom: 1px solid #e1e8ed;"><i class="fas fa-check-circle" style="color: #28a745; margin-right: 10px;"></i> Посты с текстом и медиа</li>
                    <li style="padding: 10px 0; border-bottom: 1px solid #e1e8ed;"><i class="fas fa-check-circle" style="color: #28a745; margin-right: 10px;"></i> Фотографии и видео</li>
                    <li style="padding: 10px 0;"><i class="fas fa-check-circle" style="color: #28a745; margin-right: 10px;"></i> Эмодзи и эмоции</li>
                </ul>
            </div>
            
            <div style="background: rgba(248, 249, 250, 0.8); padding: 25px; border-radius: 15px; border-left: 5px solid #2a5298;">
                <h4 style="color: #2a5298; margin-bottom: 15px;"><i class="fas fa-users"></i> Социальные функции</h4>
                <ul style="list-style: none; padding: 0;">
                    <li style="padding: 10px 0; border-bottom: 1px solid #e1e8ed;"><i class="fas fa-check-circle" style="color: #28a745; margin-right: 10px;"></i> Подписки и лента</li>
                    <li style="padding: 10px 0; border-bottom: 1px solid #e1e8ed;"><i class="fas fa-check-circle" style="color: #28a745; margin-right: 10px;"></i> Личные сообщения</li>
                    <li style="padding: 10px 0;"><i class="fas fa-check-circle" style="color: #28a745; margin-right: 10px;"></i> Лайки и комментарии</li>
                </ul>
            </div>
            
            <div style="background: rgba(248, 249, 250, 0.8); padding: 25px; border-radius: 15px; border-left: 5px solid #2a5298;">
                <h4 style="color: #2a5298; margin-bottom: 15px;"><i class="fas fa-shield-alt"></i> Безопасность</h4>
                <ul style="list-style: none; padding: 0;">
                    <li style="padding: 10px 0; border-bottom: 1px solid #e1e8ed;"><i class="fas fa-check-circle" style="color: #28a745; margin-right: 10px;"></i> Блокировка пользователей</li>
                    <li style="padding: 10px 0; border-bottom: 1px solid #e1e8ed;"><i class="fas fa-check-circle" style="color: #28a745; margin-right: 10px;"></i> Модерация контента</li>
                    <li style="padding: 10px 0;"><i class="fas fa-check-circle" style="color: #28a745; margin-right: 10px;"></i> Админ-панель</li>
                </ul>
            </div>
        </div>
    </div>
    ''')

# ========== РЕГИСТРАЦИЯ И АВТОРИЗАЦИЯ ==========
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect('/feed')
    
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        password = request.form['password']
        birthday_str = request.form.get('birthday')
        
        if not validate_username(username):
            flash('Псевдоним должен содержать только английские буквы, цифры и символы _ . -', 'error')
            return redirect('/register')
        
        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'error')
            return redirect('/register')
        
        if User.query.filter_by(username=username).first():
            flash('Псевдоним уже занят', 'error')
            return redirect('/register')
        
        birthday = None
        if birthday_str:
            try:
                birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
            except:
                pass
        
        try:
            new_user = User(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                password_hash=generate_password_hash(password),
                birthday=birthday
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            login_user(new_user, remember=True)
            flash(f'✅ Регистрация успешна! Добро пожаловать, {first_name}!', 'success')
            return redirect('/feed')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка при регистрации: {str(e)}', 'error')
            return redirect('/register')
    
    return render_page('Регистрация', '''
    <div class="card">
        <h2><i class="fas fa-user-plus"></i> Регистрация в MateuGram</h2>
        
        <form method="POST">
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-envelope"></i> Email
                </label>
                <input type="email" name="email" class="form-input" placeholder="example@mail.com" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-user"></i> Псевдоним
                </label>
                <input type="text" name="username" class="form-input" placeholder="john_doe" required>
                <small style="color: #666; display: block; margin-top: 8px;">
                    <i class="fas fa-info-circle"></i> Только английские буквы, цифры и символы _ . -
                </small>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                <div class="form-group">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-user-circle"></i> Имя
                    </label>
                    <input type="text" name="first_name" class="form-input" placeholder="Иван" required>
                </div>
                
                <div class="form-group">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-user-circle"></i> Фамилия
                    </label>
                    <input type="text" name="last_name" class="form-input" placeholder="Иванов" required>
                </div>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-birthday-cake"></i> Дата рождения
                </label>
                <input type="date" name="birthday" class="form-input">
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-lock"></i> Пароль
                </label>
                <input type="password" name="password" class="form-input" placeholder="Не менее 8 символов" required minlength="8">
            </div>
            
            <button type="submit" class="btn" style="width: 100%; padding: 18px; font-size: 18px;">
                <i class="fas fa-user-plus"></i> Создать аккаунт
            </button>
        </form>
        
        <div style="text-align: center; margin-top: 25px; padding-top: 25px; border-top: 2px solid #e1e8ed;">
            <p style="color: #666; font-size: 1.1em;">
                Уже есть аккаунт? 
                <a href="/login" style="color: #2a5298; font-weight: 600; text-decoration: none;">
                    <i class="fas fa-sign-in-alt"></i> Войти
                </a>
            </p>
        </div>
    </div>
    ''')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/feed')
    
    if request.method == 'POST':
        identifier = request.form['identifier']
        password = request.form['password']
        
        user = User.query.filter(
            (User.email == identifier) | (User.username == identifier)
        ).first()
        
        if user and check_password_hash(user.password_hash, password):
            if user.is_banned:
                flash('❌ Ваш аккаунт заблокирован', 'error')
                return redirect('/login')
            
            login_user(user, remember=True)
            
            if user.is_admin:
                flash(f'👑 Добро пожаловать, администратор {user.first_name}!', 'success')
            else:
                flash(f'Добро пожаловать, {user.first_name}!', 'success')
            
            return redirect('/feed')
        else:
            flash('Неверные данные для входа', 'error')
    
    return render_page('Вход', '''
    <div class="card">
        <h2><i class="fas fa-key"></i> Вход в MateuGram</h2>
        
        <form method="POST">
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-envelope"></i> Email или псевдоним
                </label>
                <input type="text" name="identifier" class="form-input" placeholder="example@mail.com или john_doe" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-lock"></i> Пароль
                </label>
                <input type="password" name="password" class="form-input" placeholder="Ваш пароль" required>
            </div>
            
            <button type="submit" class="btn" style="width: 100%; padding: 18px; font-size: 18px;">
                <i class="fas fa-sign-in-alt"></i> Войти
            </button>
        </form>
        
        <div style="text-align: center; margin-top: 25px; padding-top: 25px; border-top: 2px solid #e1e8ed;">
            <p style="color: #666; font-size: 1.1em;">
                Нет аккаунта? 
                <a href="/register" style="color: #2a5298; font-weight: 600; text-decoration: none;">
                    <i class="fas fa-user-plus"></i> Зарегистрироваться
                </a>
            </p>
        </div>
    </div>
    ''')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('✅ Вы успешно вышли из системы', 'success')
    return redirect('/')

# ========== ЛЕНТА И ПОСТЫ ==========
@app.route('/feed')
@login_required
def feed():
    try:
        posts = Post.query.filter_by(is_hidden=False).order_by(Post.created_at.desc()).limit(20).all()
        
        posts_html = ''
        for post in posts:
            author = User.query.get(post.user_id)
            if not author or author.is_banned:
                continue
                
            post_content = get_emoji_html(post.content)
            
            media_html = ''
            if post.images:
                images = post.images.split(',')
                if images and images[0]:
                    media_html += '<div class="media-grid">'
                    for img in images[:4]:
                        if img:
                            media_html += f'''
                            <div class="media-item">
                                <img src="/static/uploads/{img}" alt="Изображение">
                            </div>
                            '''
                    media_html += '</div>'
            
            has_liked = user_has_liked(current_user.id, post.id)
            like_btn_text = '💔 Убрать лайк' if has_liked else '❤️ Нравится'
            like_btn_class = 'btn-danger' if has_liked else ''
            
            posts_html += f'''
            <div class="post">
                <div class="post-header">
                    <div class="avatar" style="{f'background-image: url(/static/uploads/{author.avatar_filename})' if author.avatar_filename else ''}">
                        {'' if author.avatar_filename else f'{author.first_name[0]}{author.last_name[0] if author.last_name else ""}'}
                    </div>
                    <div>
                        <strong style="font-size: 1.2em; color: #2a5298;">{author.first_name} {author.last_name}</strong>
                        <div style="font-size: 0.95em; color: #666; margin-top: 5px;">
                            <i class="fas fa-at"></i> @{author.username} • 
                            <i class="fas fa-clock"></i> {post.created_at.strftime('%d.%m.%Y %H:%M')}
                        </div>
                    </div>
                </div>
                
                <p style="margin: 20px 0; font-size: 1.1em; line-height: 1.6;">{post_content}</p>
                {media_html}
                
                <div style="color: #666; font-size: 0.95em; margin-top: 15px; display: flex; gap: 20px;">
                    <span><i class="fas fa-eye"></i> {post.views_count}</span>
                    <span><i class="fas fa-heart"></i> {get_like_count(post.id)}</span>
                    <span><i class="fas fa-comment"></i> {get_comment_count(post.id)}</span>
                </div>
                
                <div class="post-actions">
                    <a href="/like/{post.id}" class="btn btn-small {like_btn_class}">
                        {like_btn_text} ({get_like_count(post.id)})
                    </a>
                    <button onclick="toggleComments({post.id})" class="btn btn-small">
                        <i class="fas fa-comment"></i> Комментировать ({get_comment_count(post.id)})
                    </button>
                    <a href="/profile/{author.id}" class="btn btn-small">
                        <i class="fas fa-user"></i> Профиль
                    </a>
                </div>
                
                <div id="comments-{post.id}" style="display: none; margin-top: 20px; padding-top: 20px; border-top: 1px solid #e1e8ed;">
                    <form method="POST" action="/add_comment/{post.id}">
                        <div class="form-group">
                            <textarea name="content" class="form-input" rows="2" placeholder="Добавить комментарий..." required></textarea>
                        </div>
                        <button type="submit" class="btn btn-small">
                            <i class="fas fa-paper-plane"></i> Отправить
                        </button>
                    </form>
                    
                    <div style="margin-top: 15px;">
                        {get_comments_html(post.id)}
                    </div>
                </div>
            </div>
            '''
    except Exception as e:
        posts_html = f'<div class="alert alert-error"><i class="fas fa-exclamation-circle"></i> Ошибка загрузки ленты: {str(e)}</div>'
    
    return render_page('Лента новостей', f'''
    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
            <h2 style="margin: 0;"><i class="fas fa-newspaper"></i> Лента новостей</h2>
            <a href="/create_post" class="btn">
                <i class="fas fa-plus-circle"></i> Новый пост
            </a>
        </div>
        
        {posts_html if posts_html else '''
        <div style="text-align: center; padding: 50px 20px;">
            <i class="fas fa-newspaper" style="font-size: 4em; color: #e1e8ed; margin-bottom: 20px;"></i>
            <h3 style="color: #666; margin-bottom: 15px;">Лента пуста</h3>
            <p style="color: #999; margin-bottom: 25px;">Будьте первым, кто опубликует пост!</p>
            <a href="/create_post" class="btn">
                <i class="fas fa-edit"></i> Создать первый пост
            </a>
        </div>
        '''}
    </div>
    ''')

def get_comments_html(post_id):
    """Генерация HTML для комментариев"""
    try:
        comments = Comment.query.filter_by(post_id=post_id).order_by(Comment.created_at.desc()).all()
        comments_html = ''
        
        for comment in comments[:10]:  # Показываем последние 10 комментариев
            author = User.query.get(comment.user_id)
            if author:
                avatar_style = f'background-image: url(/static/uploads/{author.avatar_filename})' if author.avatar_filename else ''
                avatar_text = '' if author.avatar_filename else f'{author.first_name[0]}{author.last_name[0] if author.last_name else ""}'
                
                comments_html += f'''
                <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                    <div class="avatar" style="width: 40px; height: 40px; font-size: 1em; {avatar_style}">
                        {avatar_text}
                    </div>
                    <div style="flex: 1; background: #f8f9fa; border-radius: 10px; padding: 10px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 0.9em; color: #666;">
                            <strong>{author.first_name} {author.last_name}</strong>
                            <span>{comment.created_at.strftime('%H:%M')}</span>
                        </div>
                        <p style="margin: 0;">{get_emoji_html(comment.content)}</p>
                    </div>
                </div>
                '''
        
        return comments_html if comments_html else '<p style="color: #999; text-align: center; padding: 20px;">Комментариев пока нет</p>'
    except Exception as e:
        return f'<p style="color: #999; text-align: center; padding: 20px;">Ошибка загрузки комментариев</p>'

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        
        if not content:
            flash('❌ Пост не может быть пустым', 'error')
            return redirect('/create_post')
        
        images = []
        if 'images' in request.files:
            for file in request.files.getlist('images'):
                if file.filename:
                    filename = save_file(file)
                    if filename:
                        images.append(filename)
        
        try:
            new_post = Post(
                content=content,
                user_id=current_user.id,
                images=','.join(images) if images else ''
            )
            
            db.session.add(new_post)
            db.session.commit()
            
            flash('✅ Пост успешно опубликован!', 'success')
            return redirect('/feed')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка при создании поста: {str(e)}', 'error')
            return redirect('/create_post')
    
    return render_page('Создать пост', '''
    <div class="card">
        <h2><i class="fas fa-edit"></i> Создать новый пост</h2>
        
        <form method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-comment"></i> Содержание поста
                </label>
                <textarea name="content" class="form-input" rows="6" placeholder="Что у вас нового? (поддерживаются эмодзи :), :(, <3 и т.д.)" required></textarea>
                <small style="color: #666; display: block; margin-top: 8px;">
                    <i class="fas fa-info-circle"></i> Доступные эмодзи: :) 😊, :( 😔, :D 😃, :P 😛, ;) 😉, &lt;3 ❤️
                </small>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-image"></i> Изображения
                </label>
                <input type="file" name="images" class="form-input" multiple accept="image/*">
                <small style="color: #666; display: block; margin-top: 8px;">
                    <i class="fas fa-info-circle"></i> Можно выбрать несколько файлов
                </small>
            </div>
            
            <button type="submit" class="btn" style="width: 100%; padding: 18px; font-size: 18px;">
                <i class="fas fa-paper-plane"></i> Опубликовать
            </button>
        </form>
    </div>
    ''')

@app.route('/like/<int:post_id>')
@login_required
def like_post(post_id):
    try:
        post = Post.query.get(post_id)
        if not post:
            flash('Пост не найден', 'error')
            return redirect('/feed')
        
        existing_like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
        
        if existing_like:
            db.session.delete(existing_like)
            flash('💔 Лайк убран', 'info')
        else:
            new_like = Like(user_id=current_user.id, post_id=post_id)
            db.session.add(new_like)
            flash('❤️ Лайк поставлен!', 'success')
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect('/feed')

@app.route('/add_comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    try:
        content = request.form.get('content', '').strip()
        
        if not content:
            flash('Комментарий не может быть пустым', 'error')
            return redirect('/feed')
        
        post = Post.query.get(post_id)
        if not post:
            flash('Пост не найден', 'error')
            return redirect('/feed')
        
        new_comment = Comment(
            content=content,
            user_id=current_user.id,
            post_id=post_id
        )
        
        db.session.add(new_comment)
        db.session.commit()
        
        flash('✅ Комментарий добавлен', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect('/feed')

# ========== ПРОФИЛИ ==========
@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    try:
        user = User.query.get(user_id)
        if not user or user.is_banned:
            flash('Пользователь не найден или заблокирован', 'error')
            return redirect('/users')
        
        posts = Post.query.filter_by(user_id=user_id, is_hidden=False).order_by(Post.created_at.desc()).limit(10).all()
        
        posts_html = ''
        for post in posts:
            post_content = get_emoji_html(post.content[:200] + '...' if len(post.content) > 200 else post.content)
            
            posts_html += f'''
            <div class="post">
                <div style="color: #666; font-size: 0.9em; margin-bottom: 10px;">
                    {post.created_at.strftime('%d.%m.%Y %H:%M')}
                </div>
                <p>{post_content}</p>
                <div style="color: #666; font-size: 0.95em; margin-top: 15px; display: flex; gap: 20px;">
                    <span><i class="fas fa-eye"></i> {post.views_count}</span>
                    <span><i class="fas fa-heart"></i> {get_like_count(post.id)}</span>
                    <span><i class="fas fa-comment"></i> {get_comment_count(post.id)}</span>
                </div>
                <div class="post-actions">
                    <a href="/like/{post.id}" class="btn btn-small">
                        <i class="fas fa-heart"></i> Нравится ({get_like_count(post.id)})
                    </a>
                </div>
            </div>
            '''
        
        follow_button = ''
        if current_user.id != user_id:
            if is_following(current_user.id, user_id):
                follow_button = f'''
                <a href="/unfollow/{user_id}" class="btn btn-danger">
                    <i class="fas fa-user-minus"></i> Отписаться
                </a>
                '''
            else:
                follow_button = f'''
                <a href="/follow/{user_id}" class="btn btn-success">
                    <i class="fas fa-user-plus"></i> Подписаться
                </a>
                '''
        
        avatar_style = f'background-image: url(/static/uploads/{user.avatar_filename})' if user.avatar_filename else ''
        avatar_text = '' if user.avatar_filename else f'{user.first_name[0]}{user.last_name[0] if user.last_name else ""}'
        
        birthday_info = ''
        if user.birthday:
            birthday_info = f'<p style="color: #666;"><i class="fas fa-birthday-cake"></i> Дата рождения: {user.birthday.strftime("%d.%m.%Y")}</p>'
        
        return render_page(f'Профиль {user.first_name}', f'''
        <div class="card">
            <div style="display: flex; align-items: center; margin-bottom: 30px;">
                <div class="avatar" style="width: 100px; height: 100px; font-size: 2em; {avatar_style}">
                    {avatar_text}
                </div>
                <div style="margin-left: 30px;">
                    <h2 style="margin: 0;">{user.first_name} {user.last_name}</h2>
                    <p style="color: #666; margin: 10px 0;">
                        <i class="fas fa-at"></i> @{user.username}
                        {f'<span class="admin-badge"><i class="fas fa-crown"></i> Админ</span>' if user.is_admin else ''}
                    </p>
                    <p style="color: #666;">
                        <i class="fas fa-envelope"></i> {user.email} • 
                        <i class="fas fa-calendar"></i> Зарегистрирован {user.created_at.strftime('%d.%m.%Y')}
                    </p>
                    {birthday_info}
                </div>
            </div>
            
            {f'<div class="info-box"><p><i class="fas fa-quote-left"></i> {user.bio} <i class="fas fa-quote-right"></i></p></div>' if user.bio else ''}
            
            <div class="follow-stats">
                <div class="follow-stat">
                    <div class="follow-stat-number">{get_followers_count(user_id)}</div>
                    <div class="follow-stat-label">Подписчиков</div>
                </div>
                <div class="follow-stat">
                    <div class="follow-stat-number">{get_following_count(user_id)}</div>
                    <div class="follow-stat-label">Подписок</div>
                </div>
                <div class="follow-stat">
                    <div class="follow-stat-number">{Post.query.filter_by(user_id=user_id).count()}</div>
                    <div class="follow-stat-label">Постов</div>
                </div>
            </div>
            
            <div style="display: flex; gap: 15px; margin-top: 25px; flex-wrap: wrap;">
                {follow_button}
                <a href="/messages/{user_id}" class="btn">
                    <i class="fas fa-envelope"></i> Сообщение
                </a>
                {f'<a href="/edit_profile" class="btn"><i class="fas fa-edit"></i> Редактировать профиль</a>' if current_user.id == user_id else ''}
            </div>
        </div>
        
        <div class="card">
            <h3><i class="fas fa-newspaper"></i> Последние посты</h3>
            {posts_html if posts_html else '''
            <div style="text-align: center; padding: 30px 20px; color: #999;">
                <i class="fas fa-newspaper" style="font-size: 3em; margin-bottom: 15px;"></i>
                <p>Пользователь еще не публиковал посты</p>
            </div>
            '''}
        </div>
        ''')
        
    except Exception as e:
        flash(f'Ошибка загрузки профиля: {str(e)}', 'error')
        return redirect('/users')

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        try:
            current_user.first_name = request.form.get('first_name', current_user.first_name)
            current_user.last_name = request.form.get('last_name', current_user.last_name)
            current_user.username = request.form.get('username', current_user.username)
            current_user.bio = request.form.get('bio', current_user.bio)
            
            birthday_str = request.form.get('birthday')
            if birthday_str:
                try:
                    current_user.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
                except:
                    current_user.birthday = None
            else:
                current_user.birthday = None
            
            # Проверка уникальности имени пользователя
            existing_user = User.query.filter_by(username=current_user.username).first()
            if existing_user and existing_user.id != current_user.id:
                flash('Этот псевдоним уже занят', 'error')
                return redirect('/edit_profile')
            
            if 'avatar' in request.files:
                file = request.files['avatar']
                if file and file.filename:
                    filename = save_file(file)
                    if filename:
                        current_user.avatar_filename = filename
            
            db.session.commit()
            flash('✅ Профиль успешно обновлен!', 'success')
            return redirect(f'/profile/{current_user.id}')
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка обновления профиля: {str(e)}', 'error')
    
    avatar_style = f'background-image: url(/static/uploads/{current_user.avatar_filename})' if current_user.avatar_filename else ''
    avatar_text = '' if current_user.avatar_filename else f'{current_user.first_name[0]}{current_user.last_name[0] if current_user.last_name else ""}'
    
    return render_page('Редактировать профиль', f'''
    <div class="card">
        <h2><i class="fas fa-edit"></i> Редактировать профиль</h2>
        
        <div style="text-align: center; margin-bottom: 30px;">
            <div class="avatar" style="width: 120px; height: 120px; font-size: 2.5em; margin: 0 auto; {avatar_style}">
                {avatar_text}
            </div>
        </div>
        
        <form method="POST" enctype="multipart/form-data">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                <div class="form-group">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-user-circle"></i> Имя
                    </label>
                    <input type="text" name="first_name" class="form-input" value="{current_user.first_name}" required>
                </div>
                
                <div class="form-group">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-user-circle"></i> Фамилия
                    </label>
                    <input type="text" name="last_name" class="form-input" value="{current_user.last_name}" required>
                </div>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-user"></i> Псевдоним
                </label>
                <input type="text" name="username" class="form-input" value="{current_user.username}" required>
                <small style="color: #666; display: block; margin-top: 8px;">
                    <i class="fas fa-info-circle"></i> Только английские буквы, цифры и символы _ . -
                </small>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-quote-left"></i> О себе
                </label>
                <textarea name="bio" class="form-input" rows="4" placeholder="Расскажите о себе...">{current_user.bio or ''}</textarea>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-birthday-cake"></i> Дата рождения
                </label>
                <input type="date" name="birthday" class="form-input" value="{current_user.birthday.strftime('%Y-%m-%d') if current_user.birthday else ''}">
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-image"></i> Аватар
                </label>
                <input type="file" name="avatar" class="form-input" accept="image/*">
                <small style="color: #666; display: block; margin-top: 8px;">
                    <i class="fas fa-info-circle"></i> Рекомендуемый размер: 200x200 пикселей
                </small>
            </div>
            
            <button type="submit" class="btn" style="width: 100%; padding: 18px; font-size: 18px;">
                <i class="fas fa-save"></i> Сохранить изменения
            </button>
        </form>
    </div>
    ''')

@app.route('/follow/<int:user_id>')
@login_required
def follow_user(user_id):
    try:
        if current_user.id == user_id:
            flash('Нельзя подписаться на себя', 'error')
            return redirect(f'/profile/{user_id}')
        
        if is_following(current_user.id, user_id):
            flash('Вы уже подписаны на этого пользователя', 'info')
            return redirect(f'/profile/{user_id}')
        
        user_to_follow = User.query.get(user_id)
        if not user_to_follow:
            flash('Пользователь не найден', 'error')
            return redirect('/users')
        
        new_follow = Follow(follower_id=current_user.id, followed_id=user_id)
        db.session.add(new_follow)
        db.session.commit()
        
        flash(f'✅ Вы подписались на {user_to_follow.first_name}!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(f'/profile/{user_id}')

@app.route('/unfollow/<int:user_id>')
@login_required
def unfollow_user(user_id):
    try:
        follow = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
        
        if not follow:
            flash('Вы не подписаны на этого пользователя', 'info')
            return redirect(f'/profile/{user_id}')
        
        user_to_unfollow = User.query.get(user_id)
        
        db.session.delete(follow)
        db.session.commit()
        
        flash(f'✅ Вы отписались от {user_to_unfollow.first_name}', 'info')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(f'/profile/{user_id}')

# ========== СПИСОК ПОЛЬЗОВАТЕЛЕЙ ==========
@app.route('/users')
@login_required
def users():
    try:
        search = request.args.get('search', '').strip()
        
        query = User.query.filter_by(is_banned=False)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (User.first_name.ilike(search_term)) |
                (User.last_name.ilike(search_term)) |
                (User.username.ilike(search_term))
            )
        
        users_list = query.order_by(User.created_at.desc()).all()
        
        users_html = ''
        for user in users_list:
            if user.id == current_user.id:
                continue
                
            avatar_style = f'background-image: url(/static/uploads/{user.avatar_filename})' if user.avatar_filename else ''
            avatar_text = '' if user.avatar_filename else f'{user.first_name[0]}{user.last_name[0] if user.last_name else ""}'
                
            users_html += f'''
            <div class="user-card">
                <div style="display: flex; align-items: center; margin-bottom: 15px;">
                    <div class="avatar" style="width: 50px; height: 50px; font-size: 1em; {avatar_style}">
                        {avatar_text}
                    </div>
                    <div style="margin-left: 15px;">
                        <strong style="color: #2a5298;">{user.first_name} {user.last_name}</strong>
                        <div style="font-size: 0.9em; color: #666;">
                            @{user.username}
                            {f'<span class="admin-badge">Админ</span>' if user.is_admin else ''}
                        </div>
                    </div>
                </div>
                
                <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                    <a href="/profile/{user.id}" class="btn btn-small">
                        <i class="fas fa-user"></i> Профиль
                    </a>
                    <a href="/messages/{user.id}" class="btn btn-small">
                        <i class="fas fa-envelope"></i> Сообщение
                    </a>
                    {f'<a href="/follow/{user.id}" class="btn btn-small btn-success"><i class="fas fa-user-plus"></i> Подписаться</a>' if not is_following(current_user.id, user.id) else f'<a href="/unfollow/{user.id}" class="btn btn-small btn-danger"><i class="fas fa-user-minus"></i> Отписаться</a>'}
                </div>
            </div>
            '''
        
        return render_page('Пользователи', f'''
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
                <h2 style="margin: 0;"><i class="fas fa-users"></i> Пользователи</h2>
                <form method="GET" style="display: flex; gap: 10px;">
                    <input type="text" name="search" class="form-input" placeholder="Поиск..." value="{search}">
                    <button type="submit" class="btn">
                        <i class="fas fa-search"></i> Найти
                    </button>
                </form>
            </div>
            
            {users_html if users_html else '''
            <div style="text-align: center; padding: 50px 20px;">
                <i class="fas fa-users" style="font-size: 4em; color: #e1e8ed; margin-bottom: 20px;"></i>
                <h3 style="color: #666; margin-bottom: 15px;">Пользователи не найдены</h3>
            </div>
            '''}
        </div>
        ''')
        
    except Exception as e:
        flash(f'Ошибка загрузки пользователей: {str(e)}', 'error')
        return redirect('/feed')

# ========== СООБЩЕНИЯ ==========
@app.route('/messages')
@app.route('/messages/<int:user_id>')
@login_required
def messages(user_id=None):
    try:
        if user_id:
            other_user = User.query.get(user_id)
            if not other_user or other_user.is_banned:
                flash('Пользователь не найден или заблокирован', 'error')
                return redirect('/messages')
            
            messages_list = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
                ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
            ).order_by(Message.created_at).all()
            
            # Помечаем сообщения как прочитанные
            for message in messages_list:
                if message.receiver_id == current_user.id and not message.is_read:
                    message.is_read = True
                    db.session.commit()
            
            chat_html = ''
            for message in messages_list:
                is_sent = message.sender_id == current_user.id
                chat_html += f'''
                <div style="margin-bottom: 15px; clear: both;">
                    <div style="float: {'right' if is_sent else 'left'}; text-align: {'right' if is_sent else 'left'}; max-width: 70%;">
                        <div style="background: {'#2a5298' if is_sent else '#f0f0f0'}; color: {'white' if is_sent else '#333'}; padding: 10px 15px; border-radius: 15px; display: inline-block; margin-bottom: 5px;">
                            {get_emoji_html(message.content)}
                        </div>
                        <div style="font-size: 0.8em; color: #999;">
                            {message.created_at.strftime('%H:%M %d.%m')}
                        </div>
                    </div>
                </div>
                '''
            
            avatar_style = f'background-image: url(/static/uploads/{other_user.avatar_filename})' if other_user.avatar_filename else ''
            avatar_text = '' if other_user.avatar_filename else f'{other_user.first_name[0]}{other_user.last_name[0] if other_user.last_name else ""}'
            
            return render_page(f'Чат с {other_user.first_name}', f'''
            <div class="card">
                <div style="display: flex; align-items: center; margin-bottom: 25px;">
                    <a href="/messages" class="btn btn-small" style="margin-right: 20px;">
                        <i class="fas fa-arrow-left"></i> Назад
                    </a>
                    <div class="avatar" style="width: 50px; height: 50px; {avatar_style}">
                        {avatar_text}
                    </div>
                    <div style="margin-left: 15px;">
                        <h3 style="margin: 0;">{other_user.first_name} {other_user.last_name}</h3>
                    </div>
                </div>
                
                <div style="height: 400px; overflow-y: auto; padding: 20px; background: #f8f9fa; border-radius: 15px; margin-bottom: 25px;">
                    {chat_html if chat_html else '''
                    <div style="text-align: center; padding: 50px 20px; color: #999;">
                        <i class="fas fa-comments" style="font-size: 3em; margin-bottom: 15px;"></i>
                        <p>Начните общение с этим пользователем</p>
                    </div>
                    '''}
                </div>
                
                <form method="POST" action="/send_message/{user_id}">
                    <div class="form-group">
                        <textarea name="content" class="form-input" rows="3" placeholder="Введите сообщение..." required></textarea>
                    </div>
                    <button type="submit" class="btn" style="width: 100%;">
                        <i class="fas fa-paper-plane"></i> Отправить сообщение
                    </button>
                </form>
            </div>
            ''')
        
        else:
            # Список диалогов
            sent_messages = Message.query.filter_by(sender_id=current_user.id).all()
            received_messages = Message.query.filter_by(receiver_id=current_user.id).all()
            
            all_messages = sent_messages + received_messages
            
            user_dict = {}
            for message in all_messages:
                other_id = message.sender_id if message.sender_id != current_user.id else message.receiver_id
                if other_id not in user_dict:
                    other_user = User.query.get(other_id)
                    if other_user and not other_user.is_banned:
                        last_message = message
                        unread_count = Message.query.filter_by(
                            sender_id=other_id,
                            receiver_id=current_user.id,
                            is_read=False
                        ).count()
                        
                        user_dict[other_id] = {
                            'user': other_user,
                            'last_message': last_message,
                            'unread_count': unread_count
                        }
            
            conversations_html = ''
            for other_id, data in user_dict.items():
                other_user = data['user']
                last_message = data['last_message']
                unread_count = data['unread_count']
                
                last_message_text = last_message.content if last_message else 'Нет сообщений'
                if len(last_message_text) > 50:
                    last_message_text = last_message_text[:50] + '...'
                
                avatar_style = f'background-image: url(/static/uploads/{other_user.avatar_filename})' if other_user.avatar_filename else ''
                avatar_text = '' if other_user.avatar_filename else f'{other_user.first_name[0]}{other_user.last_name[0] if other_user.last_name else ""}'
                
                conversations_html += f'''
                <a href="/messages/{other_user.id}" style="text-decoration: none; color: inherit;">
                    <div class="user-card" style="cursor: pointer;">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center;">
                                <div class="avatar" style="width: 50px; height: 50px; {avatar_style}">
                                    {avatar_text}
                                </div>
                                <div style="margin-left: 15px;">
                                    <strong style="color: #2a5298;">{other_user.first_name} {other_user.last_name}</strong>
                                    <div style="font-size: 0.9em; color: #666;">
                                        {get_emoji_html(last_message_text)}
                                    </div>
                                </div>
                            </div>
                            {f'<span style="background: #dc3545; color: white; padding: 5px 10px; border-radius: 20px; font-size: 0.8em;">{unread_count}</span>' if unread_count > 0 else ''}
                        </div>
                    </div>
                </a>
                '''
            
            unread_total = get_unread_messages_count(current_user.id)
            
            return render_page('Сообщения', f'''
            <div class="card">
                <h2><i class="fas fa-envelope"></i> Сообщения</h2>
                <p style="color: #666; margin-bottom: 20px;">
                    <i class="fas fa-bell"></i> Непрочитанных: {unread_total}
                </p>
                
                {conversations_html if conversations_html else '''
                <div style="text-align: center; padding: 50px 20px;">
                    <i class="fas fa-envelope-open" style="font-size: 4em; color: #e1e8ed; margin-bottom: 20px;"></i>
                    <h3 style="color: #666; margin-bottom: 15px;">Сообщений нет</h3>
                    <p style="color: #999;">Начните общение с другими пользователями</p>
                </div>
                '''}
            </div>
            ''')
            
    except Exception as e:
        flash(f'Ошибка загрузки сообщений: {str(e)}', 'error')
        return redirect('/feed')

@app.route('/send_message/<int:receiver_id>', methods=['POST'])
@login_required
def send_message(receiver_id):
    try:
        content = request.form.get('content', '').strip()
        
        if not content:
            flash('Сообщение не может быть пустым', 'error')
            return redirect(f'/messages/{receiver_id}')
        
        receiver = User.query.get(receiver_id)
        if not receiver:
            flash('Пользователь не найден', 'error')
            return redirect('/messages')
        
        new_message = Message(
            content=content,
            sender_id=current_user.id,
            receiver_id=receiver_id
        )
        
        db.session.add(new_message)
        db.session.commit()
        
        flash('✅ Сообщение отправлено', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(f'/messages/{receiver_id}')

# ========== АДМИН-ПАНЕЛЬ ==========
@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    try:
        total_users = User.query.count()
        total_posts = Post.query.count()
        total_comments = Comment.query.count()
        banned_users = User.query.filter_by(is_banned=True).count()
        
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        
        recent_users_html = ''
        for user in recent_users:
            recent_users_html += f'''
            <tr>
                <td>{user.id}</td>
                <td>{user.first_name} {user.last_name}</td>
                <td>@{user.username}</td>
                <td>{user.email}</td>
                <td>{user.created_at.strftime('%d.%m.%Y')}</td>
                <td>{'✅' if not user.is_banned else '❌'}</td>
                <td>
                    <a href="/admin/user/{user.id}" class="btn btn-small">
                        <i class="fas fa-edit"></i>
                    </a>
                </td>
            </tr>
            '''
        
        return render_page('Админ-панель', f'''
        <div class="card">
            <h2><i class="fas fa-crown"></i> Административная панель</h2>
            
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-number">{total_users}</div>
                    <div class="stat-label">Пользователей</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{total_posts}</div>
                    <div class="stat-label">Постов</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{total_comments}</div>
                    <div class="stat-label">Комментариев</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{banned_users}</div>
                    <div class="stat-label">Заблокированных</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h3><i class="fas fa-users"></i> Последние пользователи</h3>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Имя</th>
                        <th>Логин</th>
                        <th>Email</th>
                        <th>Дата регистрации</th>
                        <th>Статус</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {recent_users_html}
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h3><i class="fas fa-tools"></i> Инструменты администратора</h3>
            <div style="display: flex; gap: 15px; flex-wrap: wrap; margin-top: 20px;">
                <a href="/admin/backup" class="btn">
                    <i class="fas fa-database"></i> Создать бэкап
                </a>
                <a href="/admin/users" class="btn">
                    <i class="fas fa-users-cog"></i> Управление пользователями
                </a>
                <a href="/admin/stats" class="btn">
                    <i class="fas fa-chart-bar"></i> Статистика
                </a>
            </div>
        </div>
        ''')
        
    except Exception as e:
        flash(f'Ошибка загрузки админ-панели: {str(e)}', 'error')
        return redirect('/feed')

@app.route('/admin/backup')
@login_required
def admin_backup():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    if create_backup():
        flash('✅ Резервная копия успешно создана', 'success')
    else:
        flash('❌ Ошибка создания резервной копии', 'error')
    
    return redirect('/admin')

@app.route('/admin/stats')
@login_required
def admin_stats():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    try:
        total_users = User.query.count()
        total_posts = Post.query.count()
        total_comments = Comment.query.count()
        total_messages = Message.query.count()
        total_likes = Like.query.count()
        
        # Статистика по дням
        import datetime as dt
        today = dt.date.today()
        week_ago = today - dt.timedelta(days=7)
        
        recent_users = User.query.filter(User.created_at >= week_ago).count()
        recent_posts = Post.query.filter(Post.created_at >= week_ago).count()
        
        return render_page('Статистика', f'''
        <div class="card">
            <h2><i class="fas fa-chart-bar"></i> Статистика системы</h2>
            
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-number">{total_users}</div>
                    <div class="stat-label">Всего пользователей</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{total_posts}</div>
                    <div class="stat-label">Всего постов</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{total_comments}</div>
                    <div class="stat-label">Всего комментариев</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{total_messages}</div>
                    <div class="stat-label">Всего сообщений</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{total_likes}</div>
                    <div class="stat-label">Всего лайков</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{recent_users}</div>
                    <div class="stat-label">Новых за неделю</div>
                </div>
            </div>
            
            <div class="info-box" style="margin-top: 30px;">
                <h3><i class="fas fa-info-circle"></i> Информация о системе</h3>
                <p><strong>База данных:</strong> {app.config['SQLALCHEMY_DATABASE_URI']}</p>
                <p><strong>Папка загрузок:</strong> {app.config['UPLOAD_FOLDER']}</p>
                <p><strong>Макс. размер файла:</strong> {app.config['MAX_CONTENT_LENGTH'] // (1024*1024)} MB</p>
            </div>
        </div>
        ''')
        
    except Exception as e:
        flash(f'Ошибка загрузки статистики: {str(e)}', 'error')
        return redirect('/admin')

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    try:
        users_list = User.query.order_by(User.created_at.desc()).all()
        
        users_html = ''
        for user in users_list:
            users_html += f'''
            <tr>
                <td>{user.id}</td>
                <td>{user.first_name} {user.last_name}</td>
                <td>@{user.username}</td>
                <td>{user.email}</td>
                <td>{user.created_at.strftime('%d.%m.%Y')}</td>
                <td>{'✅ Админ' if user.is_admin else '👤 Пользователь'}</td>
                <td>{'❌ Забанен' if user.is_banned else '✅ Активен'}</td>
                <td>
                    <a href="/admin/user/{user.id}" class="btn btn-small">
                        <i class="fas fa-edit"></i>
                    </a>
                </td>
            </tr>
            '''
        
        return render_page('Управление пользователями', f'''
        <div class="card">
            <h2><i class="fas fa-users-cog"></i> Управление пользователями</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Имя</th>
                        <th>Логин</th>
                        <th>Email</th>
                        <th>Дата регистрации</th>
                        <th>Роль</th>
                        <th>Статус</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {users_html}
                </tbody>
            </table>
        </div>
        ''')
        
    except Exception as e:
        flash(f'Ошибка загрузки пользователей: {str(e)}', 'error')
        return redirect('/admin')

@app.route('/admin/user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_user(user_id):
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    user = User.query.get(user_id)
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect('/admin')
    
    if request.method == 'POST':
        try:
            user.first_name = request.form.get('first_name', user.first_name)
            user.last_name = request.form.get('last_name', user.last_name)
            user.email = request.form.get('email', user.email)
            user.username = request.form.get('username', user.username)
            user.is_admin = request.form.get('is_admin') == '1'
            user.is_banned = request.form.get('is_banned') == '1'
            
            birthday_str = request.form.get('birthday')
            if birthday_str:
                try:
                    user.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
                except:
                    user.birthday = None
            else:
                user.birthday = None
            
            # Проверка уникальности
            existing_user = User.query.filter_by(username=user.username).first()
            if existing_user and existing_user.id != user.id:
                flash('Этот псевдоним уже занят', 'error')
                return redirect(f'/admin/user/{user_id}')
            
            existing_email = User.query.filter_by(email=user.email).first()
            if existing_email and existing_email.id != user.id:
                flash('Этот email уже используется', 'error')
                return redirect(f'/admin/user/{user_id}')
            
            db.session.commit()
            flash('✅ Данные пользователя обновлены', 'success')
            return redirect('/admin/users')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка обновления: {str(e)}', 'error')
    
    avatar_style = f'background-image: url(/static/uploads/{user.avatar_filename})' if user.avatar_filename else ''
    avatar_text = '' if user.avatar_filename else f'{user.first_name[0]}{user.last_name[0] if user.last_name else ""}'
    
    return render_page(f'Редактирование пользователя', f'''
    <div class="card">
        <h2><i class="fas fa-user-edit"></i> Редактирование пользователя</h2>
        
        <div style="text-align: center; margin-bottom: 30px;">
            <div class="avatar" style="width: 100px; height: 100px; font-size: 2em; margin: 0 auto; {avatar_style}">
                {avatar_text}
            </div>
        </div>
        
        <form method="POST">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                <div class="form-group">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-user-circle"></i> Имя
                    </label>
                    <input type="text" name="first_name" class="form-input" value="{user.first_name}" required>
                </div>
                
                <div class="form-group">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-user-circle"></i> Фамилия
                    </label>
                    <input type="text" name="last_name" class="form-input" value="{user.last_name}" required>
                </div>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-envelope"></i> Email
                </label>
                <input type="email" name="email" class="form-input" value="{user.email}" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-user"></i> Псевдоним
                </label>
                <input type="text" name="username" class="form-input" value="{user.username}" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-birthday-cake"></i> Дата рождения
                </label>
                <input type="date" name="birthday" class="form-input" value="{user.birthday.strftime('%Y-%m-%d') if user.birthday else ''}">
            </div>
            
            <div style="display: flex; gap: 20px; margin-bottom: 20px;">
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-user-shield"></i> Администратор
                    </label>
                    <select name="is_admin" class="form-input">
                        <option value="0" {'selected' if not user.is_admin else ''}>Нет</option>
                        <option value="1" {'selected' if user.is_admin else ''}>Да</option>
                    </select>
                </div>
                
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-ban"></i> Блокировка
                    </label>
                    <select name="is_banned" class="form-input">
                        <option value="0" {'selected' if not user.is_banned else ''}>Активен</option>
                        <option value="1" {'selected' if user.is_banned else ''}>Заблокирован</option>
                    </select>
                </div>
            </div>
            
            <div style="display: flex; gap: 15px; margin-top: 25px;">
                <button type="submit" class="btn">
                    <i class="fas fa-save"></i> Сохранить
                </button>
                <a href="/admin/users" class="btn btn-danger">
                    <i class="fas fa-times"></i> Отмена
                </a>
            </div>
        </form>
    </div>
    ''')

# ========== СТАТИЧЕСКИЕ ФАЙЛЫ ==========
@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ========== ИНИЦИАЛИЗАЦИЯ И ЗАПУСК ==========
# Создаем бэкап при завершении
atexit.register(create_backup)

# Инициализация базы данных
with app.app_context():
    db.create_all()
    
    # Создаем администратора если его нет
    if User.query.count() == 0:
        print("👑 Создание первого администратора...")
        admin = User(
            email='admin@mateugram.com',
            username='Admin',
            first_name='Администратор',
            last_name='Системы',
            password_hash=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Администратор создан!")
        print("📧 Email: admin@mateugram.com")
        print("🔑 Пароль: admin123")
    
    print(f"✅ MateuGram запущен! Пользователей: {User.query.count()}, Постов: {Post.query.count()}")
    
    # Создаем начальный бэкап
    create_backup()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=False)
