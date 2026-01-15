"""
MateuGram - Синяя социальная сеть
Версия с сохранением данных между перезапусками на Render.com
ПОЛНОСТЬЮ ИСПРАВЛЕННЫЙ КОД С ВСЕМ ФУНКЦИОНАЛОМ
"""

import os
import json
import atexit
import threading
from datetime import datetime
from flask import Flask, request, redirect, url_for, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import re
import secrets

# ========== НАСТРОЙКА ПРИЛОЖЕНИЯ ==========
app = Flask(__name__)

# Настройки приложения для Render.com
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ========== УМНАЯ СИСТЕМА БАЗЫ ДАННЫХ ==========
# На Render используем /tmp который сохраняется между перезапусками
if 'RENDER' in os.environ:
    print("🌐 Обнаружен Render.com - настраиваю устойчивое хранилище...")
    
    # Файлы в /tmp сохраняются между деплоями на Render
    DB_FILE = '/tmp/mateugram_persistent.db'
    BACKUP_FILE = '/tmp/mateugram_backup.json'
    
    # Используем SQLite с файлом в /tmp
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_FILE}'
    
    print(f"🔧 База данных: {DB_FILE}")
else:
    # Локальная разработка
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mateugram.db'

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
    email_verified = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    bio = db.Column(db.Text, default='')
    avatar_filename = db.Column(db.String(200), default='default_avatar.png')
    birthday = db.Column(db.Date, nullable=True)
    feed_mode = db.Column(db.String(20), default='all')
    
    posts = db.relationship('Post', backref='author', lazy=True, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy=True, cascade='all, delete-orphan')
    views = db.relationship('View', backref='viewer', lazy=True, cascade='all, delete-orphan')
    
    blocked_users = db.relationship('BlockedUser', foreign_keys='BlockedUser.blocker_id', backref='blocker', lazy=True)
    blocked_by = db.relationship('BlockedUser', foreign_keys='BlockedUser.blocked_id', backref='blocked', lazy=True)
    
    following = db.relationship('Follow', foreign_keys='Follow.follower_id', backref='follower', lazy=True)
    followers = db.relationship('Follow', foreign_keys='Follow.followed_id', backref='followed', lazy=True)
    
    advertisements = db.relationship('Advertisement', backref='creator', lazy=True)

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_type = db.Column(db.String(20), default='text')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports_count = db.Column(db.Integer, default=0)
    is_hidden = db.Column(db.Boolean, default=False)
    views_count = db.Column(db.Integer, default=0)
    
    images = db.Column(db.Text, default='')
    videos = db.Column(db.Text, default='')
    
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy=True, cascade='all, delete-orphan')
    views = db.relationship('View', backref='post', lazy=True, cascade='all, delete-orphan')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports_count = db.Column(db.Integer, default=0)
    is_hidden = db.Column(db.Boolean, default=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class View(db.Model):
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
    reports_count = db.Column(db.Integer, default=0)
    is_hidden = db.Column(db.Boolean, default=False)

class BlockedUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Advertisement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(200))
    video_filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_notes = db.Column(db.Text, default='')
    
    show_in_feed = db.Column(db.Boolean, default=False)
    show_on_sidebar = db.Column(db.Boolean, default=False)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)

# ========== ФУНКЦИЯ load_user ==========
@login_manager.user_loader
def load_user(user_id):
    """ВАЖНО: Не фильтровать по is_banned и is_active здесь!"""
    try:
        return User.query.get(int(user_id))
    except:
        return None

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def validate_username(username):
    pattern = r'^[a-zA-Z0-9_.-]+$'
    return bool(re.match(pattern, username))

def allowed_file(filename, file_type='image'):
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
    if file and allowed_file(file.filename, file_type):
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
        ':/': '😕', ':O': '😮', ':*': '😘', '<3': '❤️', '</3': '💔',
        ':+1:': '👍', ':-1:': '👎', ':fire:': '🔥', ':100:': '💯'
    }
    
    for code, emoji in emoji_map.items():
        content = content.replace(code, emoji)
    
    return content

def is_user_blocked(blocker_id, blocked_id):
    return BlockedUser.query.filter_by(blocker_id=blocker_id, blocked_id=blocked_id).first() is not None

def get_like_count(post_id):
    return Like.query.filter_by(post_id=post_id).count()

def get_comment_count(post_id):
    return Comment.query.filter_by(post_id=post_id).count()

def is_following(follower_id, followed_id):
    return Follow.query.filter_by(follower_id=follower_id, followed_id=followed_id).first() is not None

def get_following_count(user_id):
    return Follow.query.filter_by(follower_id=user_id).count()

def get_followers_count(user_id):
    return Follow.query.filter_by(followed_id=user_id).count()

def get_unread_messages_count(user_id):
    return Message.query.filter_by(receiver_id=user_id, is_read=False).count()

def add_view(post_id, user_id):
    try:
        existing_view = View.query.filter_by(post_id=post_id, user_id=user_id).first()
        if not existing_view:
            new_view = View(post_id=post_id, user_id=user_id)
            db.session.add(new_view)
            post = Post.query.get(post_id)
            if post:
                post.views_count += 1
            db.session.commit()
            return True
    except:
        db.session.rollback()
    return False

def user_has_liked_post(user_id, post_id):
    return Like.query.filter_by(user_id=user_id, post_id=post_id).first() is not None

def get_avatar_url(user):
    if user.avatar_filename and user.avatar_filename != 'default_avatar.png':
        return f"/static/uploads/{user.avatar_filename}"
    return None

# ========== HTML ШАБЛОНЫ ==========
BASE_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MateuGram - {title}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #1e3c72; color: #333; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: white; border-radius: 15px; padding: 25px; margin-bottom: 25px; text-align: center; }
        .header h1 { color: #2a5298; margin-bottom: 10px; font-size: 2.5em; }
        .card { background: white; border-radius: 15px; padding: 30px; margin-bottom: 20px; }
        .form-group { margin-bottom: 20px; }
        .form-input { width: 100%; padding: 12px 15px; border: 2px solid #ddd; border-radius: 8px; font-size: 16px; }
        .btn { background: #2a5298; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; text-decoration: none; display: inline-block; }
        .btn:hover { background: #1e3c72; }
        .btn-danger { background: #dc3545; }
        .btn-success { background: #28a745; }
        .btn-warning { background: #ffc107; color: #000; }
        .btn-admin { background: #6f42c1; }
        .nav { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .nav-btn { background: white; color: #2a5298; border: 2px solid #2a5298; padding: 10px 20px; border-radius: 8px; text-decoration: none; }
        .nav-btn:hover { background: #2a5298; color: white; }
        .post { background: white; border-radius: 12px; padding: 20px; margin-bottom: 15px; }
        .post-header { display: flex; align-items: center; margin-bottom: 15px; }
        .avatar { width: 50px; height: 50px; border-radius: 50%; background: #2a5298; color: white; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 12px; }
        .alert { padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .alert-success { background: #d4edda; color: #155724; }
        .alert-error { background: #f8d7da; color: #721c24; }
        .alert-info { background: #d1ecf1; color: #0c5460; }
        .user-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; margin-top: 20px; }
        .user-card { background: white; border-radius: 10px; padding: 15px; }
        .admin-badge { background: #6f42c1; color: white; padding: 3px 8px; border-radius: 10px; font-size: 12px; margin-left: 5px; }
        .banned-badge { background: #dc3545; color: white; padding: 3px 8px; border-radius: 10px; font-size: 12px; margin-left: 5px; }
        .follow-stats { display: flex; gap: 20px; margin: 15px 0; }
        .follow-stat { text-align: center; padding: 10px; background: #f8f9fa; border-radius: 8px; }
        .follow-stat-number { font-size: 1.5em; font-weight: bold; color: #2a5298; }
        .follow-stat-label { font-size: 0.9em; color: #666; }
        .post-actions { display: flex; gap: 10px; margin-top: 15px; flex-wrap: wrap; }
        .btn-small { padding: 8px 12px; font-size: 14px; }
        .comments-section { margin-top: 20px; border-top: 1px solid #eee; padding-top: 15px; }
        .comment { background: #f8f9fa; border-radius: 8px; padding: 10px; margin-bottom: 10px; }
        .comment-header { display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 0.9em; color: #666; }
        .media-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin: 10px 0; }
        .media-item { border-radius: 8px; overflow: hidden; }
        .media-item img, .media-item video { width: 100%; height: 150px; object-fit: cover; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔵 MateuGram</h1>
            <p>Синяя социальная сеть для безопасного общения</p>
        </div>
        
        <div class="nav">
            <a href="/" class="nav-btn">🏠 Главная</a>
            {nav_links}
        </div>
        
        {flash_messages}
        
        {content}
    </div>
    
    <script>
    function confirmAction(action, id, name) {
        if (confirm('Вы уверены, что хотите ' + action + ' пользователя ' + name + '?')) {
            if (action === 'забанить') {
                window.location.href = '/admin/ban_user/' + id;
            } else if (action === 'разбанить') {
                window.location.href = '/admin/unban_user/' + id;
            } else if (action === 'удалить') {
                window.location.href = '/admin/delete_user/' + id;
            } else if (action === 'подписаться') {
                window.location.href = '/follow/' + id;
            } else if (action === 'отписаться') {
                window.location.href = '/unfollow/' + id;
            }
        }
    }
    
    function confirmDeletePost(postId) {
        if (confirm('Вы уверены, что хотите удалить этот пост?')) {
            window.location.href = '/delete_post/' + postId;
        }
    }
    
    function confirmDeleteComment(commentId) {
        if (confirm('Вы уверены, что хотите удалить этот комментарий?')) {
            window.location.href = '/delete_comment/' + commentId;
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
    """Рендерит страницу с заданным заголовком и содержимым"""
    
    # Генерируем навигационные ссылки
    nav_links = ''
    if current_user.is_authenticated:
        nav_links = f'''
            <a href="/feed" class="nav-btn">📰 Лента</a>
            <a href="/create_post" class="nav-btn">📝 Создать пост</a>
            <a href="/profile/{current_user.id}" class="nav-btn">👤 Мой профиль</a>
            <a href="/users" class="nav-btn">👥 Пользователи</a>
            <a href="/messages" class="nav-btn">💬 Сообщения</a>
            <a href="/create_ad" class="nav-btn">📢 Реклама</a>
        '''
        if current_user.is_admin:
            nav_links += '<a href="/admin" class="nav-btn btn-admin">👑 Админ</a>'
        nav_links += '<a href="/logout" class="nav-btn btn-danger">🚪 Выйти</a>'
    else:
        nav_links = '''
            <a href="/login" class="nav-btn">🔑 Вход</a>
            <a href="/register" class="nav-btn">📝 Регистрация</a>
        '''
    
    # Генерируем flash сообщения
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
    
    # Собираем HTML
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
    
    return render_page('Главная', '''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">Добро пожаловать в MateuGram!</h2>
        <p style="margin-bottom: 25px; line-height: 1.6;">
            Безопасная социальная сеть без политики, религии и нецензурной лексики. 
            Общайтесь с друзьями, делитесь моментами и находите единомышленников.
        </p>
        
        <div style="display: flex; gap: 15px; margin-top: 30px;">
            <a href="/register" class="btn">📝 Зарегистрироваться</a>
            <a href="/login" class="btn btn-success">🔑 Войти</a>
        </div>
    </div>
    
    <div class="card">
        <h3 style="color: #2a5298; margin-bottom: 15px;">✨ Возможности:</h3>
        <ul style="list-style: none; padding: 0;">
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Создание постов с текстом и медиа</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Подписки на пользователей</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Лента новостей</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Личные сообщения</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Админ-панель для управления</li>
            <li style="padding: 10px 0;">✅ Безопасная система без политики</li>
        </ul>
    </div>
    ''')

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
                flash('Неверный формат даты рождения', 'warning')
        
        # Если пользователь регистрируется как MateuGram, делаем его администратором
        is_admin = (username.lower() == 'mateugram')
        
        try:
            new_user = User(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                password_hash=generate_password_hash(password),
                is_admin=is_admin,
                is_active=True,
                birthday=birthday
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            login_user(new_user, remember=True)
            
            if is_admin:
                flash('✅ Регистрация успешна! Вы зарегистрированы как администратор.', 'success')
            else:
                flash(f'✅ Регистрация успешна! Добро пожаловать, {first_name}!', 'success')
            
            return redirect('/feed')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка при регистрации: {str(e)}', 'error')
            return redirect('/register')
    
    return render_page('Регистрация', '''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">Регистрация в MateuGram</h2>
        
        <form method="POST">
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📧 Email</label>
                <input type="email" name="email" class="form-input" placeholder="example@mail.com" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">👤 Псевдоним (только английские буквы)</label>
                <input type="text" name="username" class="form-input" placeholder="john_doe" required>
                <small style="color: #666; display: block; margin-top: 5px;">Разрешены: буквы a-z, цифры 0-9, символы _ . -</small>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                <div class="form-group">
                    <label style="display: block; margin-bottom: 8px; font-weight: 600;">👤 Имя</label>
                    <input type="text" name="first_name" class="form-input" placeholder="Иван" required>
                </div>
                
                <div class="form-group">
                    <label style="display: block; margin-bottom: 8px; font-weight: 600;">👤 Фамилия</label>
                    <input type="text" name="last_name" class="form-input" placeholder="Иванов" required>
                </div>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🎂 Дата рождения (опционально)</label>
                <input type="date" name="birthday" class="form-input">
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🔒 Пароль</label>
                <input type="password" name="password" class="form-input" placeholder="Не менее 8 символов" required minlength="8">
            </div>
            
            <button type="submit" class="btn">📝 Создать аккаунт</button>
        </form>
        
        <div style="text-align: center; margin-top: 20px;">
            <p>Уже есть аккаунт? <a href="/login" style="color: #2a5298;">Войти</a></p>
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
        
        # ВАЖНО: Проверяем бан только при входе, а не в load_user
        if user and check_password_hash(user.password_hash, password):
            if user.is_banned:
                flash('❌ Ваш аккаунт заблокирован администратором', 'error')
                return redirect('/login')
            
            if not user.is_active:
                flash('❌ Ваш аккаунт деактивирован', 'error')
                return redirect('/login')
            
            login_user(user, remember=True)
            
            if user.is_admin:
                flash(f'👑 Добро пожаловать, администратор {user.first_name}!', 'success')
            else:
                flash(f'Добро пожаловать, {user.first_name}!', 'success')
            
            return redirect('/feed')
        else:
            flash('Неверные email/пароль или псевдоним', 'error')
    
    return render_page('Вход', '''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">Вход в MateuGram</h2>
        
        <form method="POST">
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📧 Email или псевдоним</label>
                <input type="text" name="identifier" class="form-input" placeholder="example@mail.com или john_doe" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🔒 Пароль</label>
                <input type="password" name="password" class="form-input" placeholder="Ваш пароль" required>
            </div>
            
            <button type="submit" class="btn">🔑 Войти</button>
        </form>
        
        <div style="text-align: center; margin-top: 20px;">
            <p>Нет аккаунта? <a href="/register" style="color: #2a5298;">Зарегистрироваться</a></p>
        </div>
    </div>
    ''')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('✅ Вы вышли из системы', 'success')
    return redirect('/')

# ========== ЛЕНТА И ПОСТЫ ==========
@app.route('/feed')
@login_required
def feed():
    # Получаем посты, исключая заблокированных пользователей
    blocked_ids = [b.blocked_id for b in BlockedUser.query.filter_by(blocker_id=current_user.id).all()]
    
    if current_user.feed_mode == 'following':
        following_ids = [f.followed_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
        following_ids.append(current_user.id)
        
        posts = Post.query.filter(
            Post.is_hidden == False,
            ~Post.user_id.in_(blocked_ids),
            Post.user_id.in_(following_ids)
        ).order_by(Post.created_at.desc()).all()
    else:
        posts = Post.query.filter(
            Post.is_hidden == False,
            ~Post.user_id.in_(blocked_ids)
        ).order_by(Post.created_at.desc()).all()
    
    # Добавляем просмотры
    for post in posts:
        add_view(post.id, current_user.id)
    
    posts_html = ''
    for post in posts:
        author = User.query.get(post.user_id)
        
        # Проверяем медиа файлы
        media_html = ''
        try:
            if post.images:
                images = json.loads(post.images)
                if images:
                    media_html += '<div class="media-grid">'
                    for img in images[:4]:
                        media_html += f'<div class="media-item"><img src="/static/uploads/{img}" alt="Изображение"></div>'
                    media_html += '</div>'
            
            if post.videos:
                videos = json.loads(post.videos)
                if videos:
                    media_html += '<div class="media-grid">'
                    for vid in videos[:2]:
                        media_html += f'<div class="media-item"><video src="/static/uploads/{vid}" controls></video></div>'
                    media_html += '</div>'
        except:
            pass
        
        # Получаем комментарии для этого поста
        comments = Comment.query.filter_by(post_id=post.id, is_hidden=False).order_by(Comment.created_at.desc()).limit(3).all()
        
        comments_html = ''
        for comment in comments:
            comment_author = User.query.get(comment.user_id)
            comments_html += f'''
            <div class="comment">
                <div class="comment-header">
                    <span>{comment_author.first_name} {comment_author.last_name}</span>
                    <span>{comment.created_at.strftime('%H:%M')}</span>
                </div>
                <div>{get_emoji_html(comment.content)}</div>
                {f'<div style="margin-top: 5px;"><button onclick="confirmDeleteComment({comment.id})" class="btn btn-small btn-danger">🗑 Удалить</button></div>' if comment.user_id == current_user.id or current_user.is_admin else ''}
            </div>
            '''
        
        posts_html += f'''
        <div class="post">
            <div class="post-header">
                <div class="avatar">{author.first_name[0]}{author.last_name[0]}</div>
                <div style="flex-grow: 1;">
                    <div style="font-weight: 600; color: #2a5298;">
                        {author.first_name} {author.last_name}
                        {f'<span class="admin-badge">👑</span>' if author.is_admin else ''}
                    </div>
                    <small>@{author.username}</small>
                </div>
                <div style="color: #888; font-size: 0.9em;">{post.created_at.strftime('%d.%m.%Y %H:%M')}</div>
            </div>
            
            <div style="line-height: 1.6; margin: 15px 0;">{get_emoji_html(post.content)}</div>
            
            {media_html}
            
            <div class="post-actions">
                <a href="/like_post/{post.id}" class="btn btn-small {'btn-danger' if user_has_liked_post(current_user.id, post.id) else ''}">❤️ {get_like_count(post.id)}</a>
                <button onclick="toggleComments({post.id})" class="btn btn-small">💬 {get_comment_count(post.id)}</button>
                <span class="btn btn-small">👁️ {post.views_count}</span>
                <a href="/profile/{author.id}" class="btn btn-small">👤 Профиль</a>
                <a href="/report_post/{post.id}" class="btn btn-small btn-warning">🚫 Пожаловаться</a>
                {f'<a href="/follow/{author.id}" class="btn btn-small btn-success">➕ Подписаться</a>' if not is_following(current_user.id, author.id) and author.id != current_user.id else ''}
                {f'<button onclick="confirmDeletePost({post.id})" class="btn btn-small btn-danger">🗑 Удалить</button>' if post.user_id == current_user.id or current_user.is_admin else ''}
            </div>
            
            <!-- Форма для комментария -->
            <div style="margin-top: 15px;">
                <form method="POST" action="/add_comment/{post.id}" style="display: flex; gap: 10px;">
                    <input type="text" name="content" class="form-input" placeholder="Добавить комментарий..." required style="flex-grow: 1;">
                    <button type="submit" class="btn btn-small">Отправить</button>
                </form>
            </div>
            
            <!-- Секция комментариев -->
            <div id="comments-{post.id}" style="display: none;" class="comments-section">
                <h4 style="color: #2a5298; margin-bottom: 10px;">Комментарии:</h4>
                {comments_html if comments_html else '<p style="color: #666; text-align: center;">Комментариев пока нет.</p>'}
            </div>
        </div>
        '''
    
    if not posts_html:
        posts_html = '<p style="text-align: center; color: #666; padding: 40px;">Лента пуста. Создайте пост или подпишитесь на других пользователей!</p>'
    
    # Режим ленты
    feed_mode_html = f'''
    <div style="display: flex; gap: 10px; margin-bottom: 20px; align-items: center;">
        <span style="font-weight: 600;">Режим ленты:</span>
        <a href="/change_feed_mode/all" class="btn btn-small {'btn-success' if current_user.feed_mode == 'all' else ''}">Все посты</a>
        <a href="/change_feed_mode/following" class="btn btn-small {'btn-success' if current_user.feed_mode == 'following' else ''}">Только подписки</a>
    </div>
    '''
    
    return render_page('Лента', f'''
    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h2 style="color: #2a5298;">📰 Лента новостей</h2>
            <a href="/create_post" class="btn">📝 Создать пост</a>
        </div>
        
        {feed_mode_html}
        
        {posts_html}
    </div>
    ''')

@app.route('/change_feed_mode/<mode>')
@login_required
def change_feed_mode(mode):
    if mode in ['all', 'following']:
        current_user.feed_mode = mode
        db.session.commit()
        flash(f'✅ Режим ленты изменен на "{mode}"', 'success')
    return redirect('/feed')

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        content = request.form['content']
        
        if not content.strip():
            flash('❌ Пост должен содержать текст', 'error')
            return redirect('/create_post')
        
        # Сохраняем изображения
        images = []
        if 'images' in request.files:
            image_files = request.files.getlist('images')
            for file in image_files:
                if file.filename:
                    saved_name = save_file(file, 'image')
                    if saved_name:
                        images.append(saved_name)
        
        # Сохраняем видео
        videos = []
        if 'videos' in request.files:
            video_files = request.files.getlist('videos')
            for file in video_files:
                if file.filename:
                    saved_name = save_file(file, 'video')
                    if saved_name:
                        videos.append(saved_name)
        
        post = Post(
            content=content,
            user_id=current_user.id,
            images=json.dumps(images) if images else '',
            videos=json.dumps(videos) if videos else ''
        )
        
        db.session.add(post)
        db.session.commit()
        
        flash('✅ Пост опубликован!', 'success')
        return redirect('/feed')
    
    return render_page('Создать пост', '''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">Создать пост</h2>
        
        <form method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">💬 Что у вас нового?</label>
                <textarea name="content" class="form-input" rows="5" placeholder="Поделитесь своими мыслями..." required></textarea>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🖼️ Фотографии (до 5)</label>
                <input type="file" name="images" multiple accept="image/*">
                <small style="color: #666;">PNG, JPG, JPEG, GIF</small>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🎬 Видео (до 2)</label>
                <input type="file" name="videos" multiple accept="video/*">
                <small style="color: #666;">MP4, MOV, AVI, MKV</small>
            </div>
            
            <button type="submit" class="btn">📤 Опубликовать</button>
            <a href="/feed" class="btn btn-danger" style="margin-left: 10px;">❌ Отмена</a>
        </form>
    </div>
    ''')

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if post.user_id != current_user.id and not current_user.is_admin:
        flash('❌ Вы не можете удалить этот пост', 'error')
        return redirect('/feed')
    
    # Удаляем медиа файлы
    try:
        if post.images:
            images = json.loads(post.images)
            for img in images:
                img_path = os.path.join(app.config['UPLOAD_FOLDER'], img)
                if os.path.exists(img_path):
                    os.remove(img_path)
        
        if post.videos:
            videos = json.loads(post.videos)
            for vid in videos:
                vid_path = os.path.join(app.config['UPLOAD_FOLDER'], vid)
                if os.path.exists(vid_path):
                    os.remove(vid_path)
    except:
        pass
    
    db.session.delete(post)
    db.session.commit()
    
    flash('✅ Пост удален', 'success')
    return redirect('/feed')

@app.route('/like_post/<int:post_id>')
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if user_has_liked_post(current_user.id, post_id):
        # Удаляем лайк
        like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
        if like:
            db.session.delete(like)
            db.session.commit()
            flash('💔 Вы убрали лайк', 'info')
    else:
        # Добавляем лайк
        like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(like)
        db.session.commit()
        flash('❤️ Вы поставили лайк', 'success')
    
    return redirect('/feed')

@app.route('/add_comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    
    content = request.form['content']
    if not content.strip():
        flash('❌ Комментарий не может быть пустым', 'error')
        return redirect('/feed')
    
    comment = Comment(
        content=content,
        user_id=current_user.id,
        post_id=post_id
    )
    
    db.session.add(comment)
    db.session.commit()
    
    flash('✅ Комментарий добавлен', 'success')
    return redirect('/feed')

@app.route('/delete_comment/<int:comment_id>')
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    
    if comment.user_id != current_user.id and not current_user.is_admin:
        flash('❌ Вы не можете удалить этот комментарий', 'error')
        return redirect('/feed')
    
    db.session.delete(comment)
    db.session.commit()
    
    flash('✅ Комментарий удален', 'success')
    return redirect('/feed')

@app.route('/report_post/<int:post_id>')
@login_required
def report_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if post.user_id == current_user.id:
        flash('❌ Нельзя пожаловаться на свой собственный пост', 'error')
        return redirect('/feed')
    
    post.reports_count += 1
    db.session.commit()
    
    flash('✅ Жалоба отправлена администраторам', 'success')
    return redirect('/feed')

@app.route('/report_message/<int:message_id>')
@login_required
def report_message(message_id):
    message = Message.query.get_or_404(message_id)
    
    if message.sender_id == current_user.id:
        flash('❌ Нельзя пожаловаться на свое собственное сообщение', 'error')
        return redirect(f'/messages/{message.receiver_id if message.sender_id == current_user.id else message.sender_id}')
    
    message.reports_count += 1
    db.session.commit()
    
    flash('✅ Жалоба на сообщение отправлена администраторам', 'success')
    return redirect(f'/messages/{message.receiver_id if message.sender_id == current_user.id else message.sender_id}')

# ========== ПРОФИЛЬ ==========
@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)
    
    if is_user_blocked(current_user.id, user_id):
        return render_page('Профиль', '''
        <div class="card">
            <p style="text-align: center; color: #666; padding: 40px;">🚫 Вы заблокировали этого пользователя</p>
            <div style="text-align: center;">
                <a href="/users" class="btn">← Назад к пользователям</a>
            </div>
        </div>
        ''')
    
    user_posts = Post.query.filter_by(user_id=user_id, is_hidden=False).order_by(Post.created_at.desc()).all()
    is_following_user = is_following(current_user.id, user_id)
    
    # Отображаем аватар
    avatar_html = ''
    avatar_url = get_avatar_url(user)
    if avatar_url:
        avatar_html = f'<img src="{avatar_url}" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover;">'
    else:
        avatar_html = f'<div class="avatar" style="width: 100px; height: 100px; font-size: 2em;">{user.first_name[0]}{user.last_name[0]}</div>'
    
    posts_html = ''
    for post in user_posts[:5]:  # Показываем только 5 последних постов
        posts_html += f'''
        <div class="post">
            <div style="color: #888; text-align: right; font-size: 0.9em;">{post.created_at.strftime('%d.%m.%Y %H:%M')}</div>
            <div style="line-height: 1.6; margin: 10px 0;">{get_emoji_html(post.content)}</div>
            <div class="post-actions">
                <span class="btn btn-small">❤️ {get_like_count(post.id)}</span>
                <span class="btn btn-small">💬 {get_comment_count(post.id)}</span>
                <span class="btn btn-small">👁️ {post.views_count}</span>
            </div>
        </div>
        '''
    
    if not posts_html:
        posts_html = '<p style="text-align: center; color: #666;">У пользователя пока нет постов.</p>'
    
    # Кнопки действий
    action_buttons = ''
    if user_id == current_user.id:
        action_buttons = f'''
        <a href="/edit_profile" class="btn btn-warning">✏️ Редактировать профиль</a>
        '''
    else:
        if is_user_blocked(user_id, current_user.id):
            action_buttons = '<span class="btn btn-danger">🚫 Пользователь заблокировал вас</span>'
        else:
            if is_following_user:
                action_buttons = f'''
                <a href="/unfollow/{user_id}" class="btn btn-danger">❌ Отписаться</a>
                <a href="/messages/{user_id}" class="btn btn-success">💬 Написать</a>
                '''
            else:
                action_buttons = f'''
                <a href="/follow/{user_id}" class="btn btn-success">➕ Подписаться</a>
                <a href="/messages/{user_id}" class="btn">💬 Написать</a>
                '''
            # Кнопка блокировки
            if not is_user_blocked(current_user.id, user_id):
                action_buttons += f'<a href="/block_user/{user_id}" class="btn btn-danger">🚫 Заблокировать</a>'
            else:
                action_buttons += f'<a href="/unblock_user/{user_id}" class="btn btn-success">✅ Разблокировать</a>'
    
    # Бейджи
    badges = ''
    if user.is_admin:
        badges += '<span class="admin-badge">👑 Администратор</span> '
    if user.is_banned:
        badges += '<span class="banned-badge">🚫 Забанен</span>'
    
    return render_page(f'Профиль {user.username}', f'''
    <div class="card">
        <div style="display: flex; align-items: center; gap: 25px; margin-bottom: 25px;">
            <div>
                {avatar_html}
            </div>
            <div style="flex-grow: 1;">
                <h2 style="color: #2a5298; margin-bottom: 5px;">
                    {user.first_name} {user.last_name}
                    {badges}
                </h2>
                <p>@{user.username}</p>
                <p>📧 {user.email}</p>
                {f'<p>🎂 Дата рождения: {user.birthday.strftime("%d.%m.%Y") if user.birthday else "Не указана"}</p>'}
                <p>📅 Зарегистрирован: {user.created_at.strftime("%d.%m.%Y")}</p>
                
                <div class="follow-stats">
                    <div class="follow-stat">
                        <div class="follow-stat-number">{len(user_posts)}</div>
                        <div class="follow-stat-label">Постов</div>
                    </div>
                    <div class="follow-stat">
                        <div class="follow-stat-number">{get_followers_count(user_id)}</div>
                        <div class="follow-stat-label">Подписчиков</div>
                    </div>
                    <div class="follow-stat">
                        <div class="follow-stat-number">{get_following_count(user_id)}</div>
                        <div class="follow-stat-label">Подписок</div>
                    </div>
                </div>
                
                <div style="margin-top: 20px; display: flex; gap: 10px; flex-wrap: wrap;">
                    {action_buttons}
                    <a href="/users" class="btn">← Назад</a>
                </div>
            </div>
        </div>
        
        {f'<div class="card" style="margin-top: 20px;"><h3 style="color: #2a5298; margin-bottom: 15px;">📝 О себе</h3><p style="line-height: 1.6;">{get_emoji_html(user.bio) if user.bio else "Пользователь не добавил информацию о себе."}</p></div>' if user.bio else ''}
        
        <div style="margin-top: 30px;">
            <h3 style="color: #2a5298; margin-bottom: 15px;">📰 Последние посты</h3>
            {posts_html}
        </div>
    </div>
    ''')

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name', current_user.first_name)
        current_user.last_name = request.form.get('last_name', current_user.last_name)
        current_user.username = request.form.get('username', current_user.username)
        current_user.email = request.form.get('email', current_user.email)
        current_user.bio = request.form.get('bio', current_user.bio)
        
        birthday_str = request.form.get('birthday')
        if birthday_str:
            try:
                current_user.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
            except:
                flash('Неверный формат даты рождения', 'warning')
        
        new_password = request.form.get('new_password')
        if new_password and new_password.strip():
            if len(new_password) < 8:
                flash('❌ Пароль должен содержать минимум 8 символов', 'error')
                return redirect('/edit_profile')
            current_user.password_hash = generate_password_hash(new_password)
            flash('✅ Пароль изменен', 'success')
        
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file.filename:
                saved_name = save_file(file, 'image')
                if saved_name:
                    # Удаляем старый аватар, если он не стандартный
                    if current_user.avatar_filename and current_user.avatar_filename != 'default_avatar.png':
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.avatar_filename)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    
                    current_user.avatar_filename = saved_name
                    flash('✅ Аватар обновлен', 'success')
        
        db.session.commit()
        flash('✅ Профиль успешно обновлен', 'success')
        return redirect(f'/profile/{current_user.id}')
    
    # Отображаем текущий аватар
    avatar_html = ''
    avatar_url = get_avatar_url(current_user)
    if avatar_url:
        avatar_html = f'<img src="{avatar_url}" style="width: 80px; height: 80px; border-radius: 50%; object-fit: cover;">'
    else:
        avatar_html = f'<div class="avatar" style="width: 80px; height: 80px; font-size: 1.5em;">{current_user.first_name[0]}{current_user.last_name[0]}</div>'
    
    birthday_str = current_user.birthday.strftime('%Y-%m-%d') if current_user.birthday else ''
    
    return render_page('Редактирование профиля', f'''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">Редактирование профиля</h2>
        
        <form method="POST" enctype="multipart/form-data">
            <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 30px;">
                <div>
                    {avatar_html}
                </div>
                <div>
                    <label style="display: block; margin-bottom: 8px; font-weight: 600;">🖼️ Аватар</label>
                    <input type="file" name="avatar" accept="image/*">
                    <small style="color: #666;">Максимальный размер: 5MB</small>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                <div class="form-group">
                    <label style="display: block; margin-bottom: 8px; font-weight: 600;">👤 Имя</label>
                    <input type="text" name="first_name" class="form-input" value="{current_user.first_name}" required>
                </div>
                
                <div class="form-group">
                    <label style="display: block; margin-bottom: 8px; font-weight: 600;">👤 Фамилия</label>
                    <input type="text" name="last_name" class="form-input" value="{current_user.last_name}" required>
                </div>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">👤 Псевдоним</label>
                <input type="text" name="username" class="form-input" value="{current_user.username}" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📧 Email</label>
                <input type="email" name="email" class="form-input" value="{current_user.email}" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🎂 Дата рождения</label>
                <input type="date" name="birthday" class="form-input" value="{birthday_str}">
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📝 О себе</label>
                <textarea name="bio" class="form-input" rows="4" placeholder="Расскажите о себе...">{current_user.bio}</textarea>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🔒 Новый пароль (оставьте пустым, если не хотите менять)</label>
                <input type="password" name="new_password" class="form-input" placeholder="Новый пароль (мин. 8 символов)">
            </div>
            
            <div style="display: flex; gap: 10px; margin-top: 30px;">
                <button type="submit" class="btn">💾 Сохранить изменения</button>
                <a href="/profile/{current_user.id}" class="btn btn-danger">❌ Отмена</a>
            </div>
        </form>
    </div>
    ''')

@app.route('/block_user/<int:user_id>')
@login_required
def block_user(user_id):
    if user_id == current_user.id:
        flash('❌ Нельзя заблокировать самого себя', 'error')
        return redirect(f'/profile/{user_id}')
    
    if is_user_blocked(current_user.id, user_id):
        flash('❌ Вы уже заблокировали этого пользователя', 'error')
        return redirect(f'/profile/{user_id}')
    
    blocked = BlockedUser(blocker_id=current_user.id, blocked_id=user_id)
    db.session.add(blocked)
    db.session.commit()
    
    user = User.query.get(user_id)
    flash(f'✅ Вы заблокировали {user.first_name} {user.last_name}', 'success')
    return redirect(f'/profile/{user_id}')

@app.route('/unblock_user/<int:user_id>')
@login_required
def unblock_user(user_id):
    if user_id == current_user.id:
        flash('❌ Нельзя разблокировать самого себя', 'error')
        return redirect(f'/profile/{user_id}')
    
    blocked = BlockedUser.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).first()
    if not blocked:
        flash('❌ Вы не блокировали этого пользователя', 'error')
        return redirect(f'/profile/{user_id}')
    
    db.session.delete(blocked)
    db.session.commit()
    
    user = User.query.get(user_id)
    flash(f'✅ Вы разблокировали {user.first_name} {user.last_name}', 'success')
    return redirect(f'/profile/{user_id}')

# ========== ПОЛЬЗОВАТЕЛИ ==========
@app.route('/users')
@login_required
def users():
    search_query = request.args.get('search', '')
    
    blocked_ids = [b.blocked_id for b in BlockedUser.query.filter_by(blocker_id=current_user.id).all()]
    
    if search_query:
        users_list = User.query.filter(
            ((User.first_name.ilike(f'%{search_query}%')) |
            (User.last_name.ilike(f'%{search_query}%')) |
            (User.username.ilike(f'%{search_query}%'))) &
            (~User.id.in_(blocked_ids)) &
            (User.id != current_user.id)
        ).all()
    else:
        users_list = User.query.filter(~User.id.in_(blocked_ids), User.id != current_user.id).all()
    
    users_html = ''
    for user in users_list:
        posts_count = Post.query.filter_by(user_id=user.id).count()
        is_following_user = is_following(current_user.id, user.id)
        
        # Аватар пользователя
        avatar_html = ''
        avatar_url = get_avatar_url(user)
        if avatar_url:
            avatar_html = f'<img src="{avatar_url}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;">'
        else:
            avatar_html = f'<div class="avatar">{user.first_name[0]}{user.last_name[0]}</div>'
        
        users_html += f'''
        <div class="user-card">
            <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                {avatar_html}
                <div style="flex-grow: 1;">
                    <div style="font-weight: bold; color: #2a5298;">
                        {user.first_name} {user.last_name}
                        {f'<span class="admin-badge">👑</span>' if user.is_admin else ''}
                    </div>
                    <small>@{user.username}</small>
                </div>
            </div>
            <div style="color: #666; font-size: 0.9em; margin-bottom: 10px;">
                📝 {posts_count} постов • 👥 {get_followers_count(user.id)} подписчиков
            </div>
            <div style="display: flex; gap: 5px; flex-wrap: wrap;">
                <a href="/profile/{user.id}" class="btn btn-small">👤 Профиль</a>
                <a href="/messages/{user.id}" class="btn btn-small btn-success">💬 Написать</a>
                {f'<a href="/unfollow/{user.id}" class="btn btn-small btn-danger">❌ Отписаться</a>' if is_following_user else f'<a href="/follow/{user.id}" class="btn btn-small btn-success">➕ Подписаться</a>'}
            </div>
        </div>
        '''
    
    if not users_html:
        users_html = '<p style="text-align: center; color: #666; padding: 40px;">Пользователи не найдены.</p>'
    
    return render_page('Пользователи', f'''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">👥 Пользователи MateuGram</h2>
        
        <form method="GET" action="/users" style="margin-bottom: 25px;">
            <div class="form-group">
                <input type="text" name="search" class="form-input" placeholder="🔍 Поиск по имени, фамилии или нику..." value="{search_query}">
            </div>
            <button type="submit" class="btn">🔍 Искать</button>
        </form>
        
        <div class="user-list">
            {users_html}
        </div>
    </div>
    ''')

@app.route('/follow/<int:user_id>')
@login_required
def follow(user_id):
    if user_id == current_user.id:
        flash('❌ Нельзя подписаться на самого себя', 'error')
        return redirect(f'/profile/{user_id}')
    
    if is_user_blocked(current_user.id, user_id):
        flash('🚫 Вы заблокировали этого пользователя', 'error')
        return redirect(f'/profile/{user_id}')
    
    if is_following(current_user.id, user_id):
        flash('❌ Вы уже подписаны на этого пользователя', 'error')
        return redirect(f'/profile/{user_id}')
    
    follow_record = Follow(follower_id=current_user.id, followed_id=user_id)
    db.session.add(follow_record)
    db.session.commit()
    
    user = User.query.get(user_id)
    flash(f'✅ Вы подписались на {user.first_name} {user.last_name}', 'success')
    return redirect(f'/profile/{user_id}')

@app.route('/unfollow/<int:user_id>')
@login_required
def unfollow(user_id):
    if user_id == current_user.id:
        flash('❌ Нельзя отписаться от самого себя', 'error')
        return redirect(f'/profile/{user_id}')
    
    follow_record = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
    if not follow_record:
        flash('❌ Вы не подписаны на этого пользователя', 'error')
        return redirect(f'/profile/{user_id}')
    
    db.session.delete(follow_record)
    db.session.commit()
    
    user = User.query.get(user_id)
    flash(f'✅ Вы отписались от {user.first_name} {user.last_name}', 'success')
    return redirect(f'/profile/{user_id}')

# ========== СООБЩЕНИЯ ==========
@app.route('/messages')
@login_required
def messages_list():
    unread_count = get_unread_messages_count(current_user.id)
    
    # Получаем последние диалоги
    sent_messages = Message.query.filter_by(sender_id=current_user.id).order_by(Message.created_at.desc()).all()
    received_messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.created_at.desc()).all()
    
    # Собираем уникальных собеседников
    interlocutors = {}
    for msg in sent_messages + received_messages:
        other_id = msg.receiver_id if msg.sender_id == current_user.id else msg.sender_id
        if other_id not in interlocutors:
            user = User.query.get(other_id)
            if user:
                interlocutors[other_id] = {
                    'user': user,
                    'last_message': msg,
                    'unread': msg.receiver_id == current_user.id and not msg.is_read
                }
    
    dialogues_html = ''
    for other_id, data in list(interlocutors.items())[:10]:  # Показываем 10 последних диалогов
        user = data['user']
        last_msg = data['last_message']
        unread = data['unread']
        
        avatar_html = ''
        avatar_url = get_avatar_url(user)
        if avatar_url:
            avatar_html = f'<img src="{avatar_url}" style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;">'
        else:
            avatar_html = f'<div class="avatar" style="width: 40px; height: 40px; font-size: 0.8em;">{user.first_name[0]}{user.last_name[0]}</div>'
        
        dialogues_html += f'''
        <div style="background: {'#e3f2fd' if unread else 'white'}; border-radius: 10px; padding: 15px; margin-bottom: 10px; display: flex; align-items: center; gap: 15px;">
            {avatar_html}
            <div style="flex-grow: 1;">
                <div style="font-weight: {'bold' if unread else 'normal'}; color: #2a5298;">
                    {user.first_name} {user.last_name}
                    {f'<span style="background: #dc3545; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.8em; margin-left: 5px;">Новое</span>' if unread else ''}
                </div>
                <div style="color: #666; font-size: 0.9em;">
                    {last_msg.content[:50]}{'...' if len(last_msg.content) > 50 else ''}
                </div>
            </div>
            <div>
                <a href="/messages/{user.id}" class="btn btn-small">💬 Открыть</a>
            </div>
        </div>
        '''
    
    if not dialogues_html:
        dialogues_html = '<p style="text-align: center; color: #666; padding: 20px;">У вас пока нет диалогов.</p>'
    
    return render_page('Сообщения', f'''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">💬 Сообщения</h2>
        <p style="margin-bottom: 20px; color: #666;">
            {f'У вас {unread_count} непрочитанных сообщений' if unread_count > 0 else 'Нет непрочитанных сообщений'}
        </p>
        
        <div style="margin-bottom: 20px;">
            <h3 style="color: #2a5298; margin-bottom: 15px;">📨 Последние диалоги</h3>
            {dialogues_html}
        </div>
        
        <div style="text-align: center; margin-top: 20px;">
            <a href="/users" class="btn">👥 Найти пользователей для общения</a>
        </div>
    </div>
    ''')

@app.route('/messages/<int:receiver_id>', methods=['GET', 'POST'])
@login_required
def messages(receiver_id):
    receiver = User.query.get_or_404(receiver_id)
    
    if receiver_id == current_user.id:
        flash('❌ Нельзя написать самому себе', 'error')
        return redirect('/messages')
    
    if is_user_blocked(current_user.id, receiver_id) or is_user_blocked(receiver_id, current_user.id):
        flash('🚫 Вы не можете общаться с этим пользователем', 'error')
        return redirect('/messages')
    
    if request.method == 'POST':
        content = request.form['content']
        
        if not content.strip():
            flash('❌ Сообщение не может быть пустым', 'error')
            return redirect(f'/messages/{receiver_id}')
        
        message = Message(
            content=content,
            sender_id=current_user.id,
            receiver_id=receiver_id
        )
        
        db.session.add(message)
        db.session.commit()
        
        return redirect(f'/messages/{receiver_id}')
    
    # Получаем историю сообщений
    messages_history = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == receiver_id)) |
        ((Message.sender_id == receiver_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at).all()
    
    # Помечаем как прочитанные
    for msg in messages_history:
        if msg.receiver_id == current_user.id and not msg.is_read:
            msg.is_read = True
    db.session.commit()
    
    messages_html = ''
    for msg in messages_history:
        message_class = 'sent' if msg.sender_id == current_user.id else 'received'
        sender = User.query.get(msg.sender_id)
        
        messages_html += f'''
        <div style="background: {'#e3f2fd' if message_class == 'sent' else '#f1f8e9'}; 
                    border-left: 4px solid {'#2196f3' if message_class == 'sent' else '#4caf50'};
                    border-radius: 10px; padding: 15px; margin-bottom: 10px;
                    {'margin-left: 50px;' if message_class == 'sent' else 'margin-right: 50px;'}">
            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.9em; color: #666;">
                <span>{sender.first_name} {sender.last_name}</span>
                <span>{msg.created_at.strftime('%H:%M')}</span>
            </div>
            <div style="line-height: 1.5;">{get_emoji_html(msg.content)}</div>
            <div style="margin-top: 10px; display: flex; gap: 5px;">
                {f'<a href="/report_message/{msg.id}" class="btn btn-small btn-warning">🚫 Пожаловаться</a>' if msg.sender_id != current_user.id else ''}
            </div>
        </div>
        '''
    
    if not messages_html:
        messages_html = '<p style="text-align: center; color: #666; padding: 20px;">Нет сообщений. Начните диалог!</p>'
    
    # Аватар получателя
    receiver_avatar = ''
    receiver_avatar_url = get_avatar_url(receiver)
    if receiver_avatar_url:
        receiver_avatar = f'<img src="{receiver_avatar_url}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover; margin-right: 15px;">'
    else:
        receiver_avatar = f'<div class="avatar" style="margin-right: 15px;">{receiver.first_name[0]}{receiver.last_name[0]}</div>'
    
    return render_page(f'Диалог с {receiver.username}', f'''
    <div class="card">
        <div style="display: flex; align-items: center; margin-bottom: 25px;">
            {receiver_avatar}
            <div>
                <h2 style="color: #2a5298; margin-bottom: 5px;">💬 Диалог с {receiver.first_name} {receiver.last_name}</h2>
                <p>@{receiver.username}</p>
            </div>
        </div>
        
        <div style="max-height: 400px; overflow-y: auto; margin-bottom: 20px;">
            {messages_html}
        </div>
        
        <form method="POST" action="/messages/{receiver_id}">
            <div class="form-group">
                <textarea name="content" class="form-input" rows="3" placeholder="Введите сообщение..." required></textarea>
            </div>
            
            <div style="display: flex; gap: 10px;">
                <button type="submit" class="btn">📤 Отправить</button>
                <a href="/messages" class="btn">← Назад к диалогам</a>
            </div>
        </form>
    </div>
    ''')

# ========== РЕКЛАМА ==========
@app.route('/create_ad', methods=['GET', 'POST'])
@login_required
def create_ad():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        
        if not title.strip() or not description.strip():
            flash('❌ Заполните все обязательные поля', 'error')
            return redirect('/create_ad')
        
        image_filename = None
        video_filename = None
        
        if 'image' in request.files:
            file = request.files['image']
            if file.filename:
                saved_name = save_file(file, 'image')
                if saved_name:
                    image_filename = saved_name
        
        if 'video' in request.files:
            file = request.files['video']
            if file.filename:
                saved_name = save_file(file, 'video')
                if saved_name:
                    video_filename = saved_name
        
        ad = Advertisement(
            user_id=current_user.id,
            title=title,
            description=description,
            image_filename=image_filename,
            video_filename=video_filename,
            status='pending'
        )
        
        db.session.add(ad)
        db.session.commit()
        
        flash('✅ Рекламное предложение отправлено на модерацию', 'success')
        return redirect('/feed')
    
    return render_page('Создать рекламу', '''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">📢 Создать рекламное предложение</h2>
        
        <form method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📝 Заголовок</label>
                <input type="text" name="title" class="form-input" placeholder="Заголовок вашей рекламы" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📄 Описание</label>
                <textarea name="description" class="form-input" rows="5" placeholder="Подробное описание вашего предложения..." required></textarea>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🖼️ Изображение (опционально)</label>
                <input type="file" name="image" accept="image/*">
                <small style="color: #666;">PNG, JPG, JPEG, GIF</small>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🎬 Видео (опционально)</label>
                <input type="file" name="video" accept="video/*">
                <small style="color: #666;">MP4, MOV, AVI, MKV</small>
            </div>
            
            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <h4 style="color: #2a5298; margin-bottom: 10px;">📋 Правила размещения рекламы:</h4>
                <ul style="list-style: none; padding: 0; color: #666;">
                    <li>✅ Реклама не должна содержать запрещенный контент</li>
                    <li>✅ Запрещена политическая и религиозная реклама</li>
                    <li>✅ Все предложения проходят модерацию</li>
                    <li>✅ Срок рассмотрения: 1-3 рабочих дня</li>
                </ul>
            </div>
            
            <button type="submit" class="btn">📤 Отправить на модерацию</button>
            <a href="/feed" class="btn btn-danger" style="margin-left: 10px;">❌ Отмена</a>
        </form>
    </div>
    ''')

# ========== АДМИН-ПАНЕЛЬ ==========
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True, is_banned=False).count()
    banned_users = User.query.filter_by(is_banned=True).count()
    total_posts = Post.query.count()
    total_messages = Message.query.count()
    pending_ads = Advertisement.query.filter_by(status='pending').count()
    
    return render_page('Админ-панель', f'''
    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 20px;">👑 Панель администратора</h2>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px;">
            <div style="background: #e7f3ff; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #2a5298;">{total_users}</h3>
                <p>Всего пользователей</p>
            </div>
            <div style="background: #d4edda; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #28a745;">{active_users}</h3>
                <p>Активных</p>
            </div>
            <div style="background: #f8d7da; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #dc3545;">{banned_users}</h3>
                <p>Забаненных</p>
            </div>
            <div style="background: #fff3cd; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #856404;">{total_posts}</h3>
                <p>Всего постов</p>
            </div>
            <div style="background: #d1ecf1; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #0c5460;">{pending_ads}</h3>
                <p>Ожидающих реклам</p>
            </div>
        </div>
        
        <div style="display: flex; flex-direction: column; gap: 10px;">
            <a href="/admin/users" class="btn btn-admin">👥 Управление пользователями</a>
            <a href="/admin/reports" class="btn btn-admin">📊 Жалобы</a>
            <a href="/admin/ads" class="btn btn-admin">📢 Модерация рекламы</a>
            <a href="/feed" class="btn">← Назад в ленту</a>
        </div>
    </div>
    ''')

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    search_query = request.args.get('search', '')
    
    if search_query:
        users_list = User.query.filter(
            (User.first_name.ilike(f'%{search_query}%')) |
            (User.last_name.ilike(f'%{search_query}%')) |
            (User.username.ilike(f'%{search_query}%')) |
            (User.email.ilike(f'%{search_query}%'))
        ).all()
    else:
        users_list = User.query.all()
    
    users_html = ''
    for user in users_list:
        posts_count = Post.query.filter_by(user_id=user.id).count()
        following_count = get_following_count(user.id)
        followers_count = get_followers_count(user.id)
        
        # Аватар пользователя
        avatar_html = ''
        avatar_url = get_avatar_url(user)
        if avatar_url:
            avatar_html = f'<img src="{avatar_url}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;">'
        else:
            avatar_html = f'<div class="avatar">{user.first_name[0]}{user.last_name[0]}</div>'
        
        users_html += f'''
        <div class="card" style="margin-bottom: 15px; position: relative;">
            <div style="display: flex; align-items: center; gap: 15px;">
                {avatar_html}
                <div style="flex-grow: 1;">
                    <div style="font-weight: bold; color: #2a5298;">
                        {user.first_name} {user.last_name}
                        {f'<span class="admin-badge">👑</span>' if user.is_admin else ''}
                        {f'<span class="banned-badge">🚫</span>' if user.is_banned else ''}
                    </div>
                    <small>@{user.username} • 📧 {user.email}</small>
                    <div style="margin-top: 5px; font-size: 0.9em; color: #666;">
                        📅 {user.created_at.strftime('%d.%m.%Y %H:%M')}
                    </div>
                    <div style="margin-top: 5px; font-size: 0.8em; color: #666; background: #f8f9fa; padding: 5px; border-radius: 5px;">
                        📝 {posts_count} постов • 👥 {followers_count} подписчиков • ➕ {following_count} подписок
                    </div>
                </div>
            </div>
            
            <div style="display: flex; gap: 5px; margin-top: 10px; flex-wrap: wrap;">
                <a href="/profile/{user.id}" class="btn btn-small">👤 Профиль</a>
                {f'<a href="/admin/unban_user/{user.id}" class="btn btn-small btn-success">✅ Разбанить</a>' if user.is_banned and user.id != current_user.id else ''}
                {f'<a href="/admin/ban_user/{user.id}" class="btn btn-small btn-danger">🚫 Забанить</a>' if not user.is_banned and user.id != current_user.id else ''}
                {f'<button onclick="confirmAction(\'удалить\', {user.id}, \'{user.username}\')" class="btn btn-small btn-danger">🗑 Удалить</button>' if user.id != current_user.id else ''}
                {f'<a href="/admin/make_admin/{user.id}" class="btn btn-small btn-admin">👑 Назначить админом</a>' if not user.is_admin and user.id != current_user.id else ''}
                {f'<a href="/admin/remove_admin/{user.id}" class="btn btn-small btn-warning">👑 Снять права</a>' if user.is_admin and user.id != current_user.id else ''}
            </div>
        </div>
        '''
    
    if not users_html:
        users_html = '<p style="text-align: center; color: #666; padding: 40px;">Пользователи не найдены.</p>'
    
    return render_page('Админ - Пользователи', f'''
    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 25px;">👑 Управление пользователями</h2>
        
        <form method="GET" action="/admin/users" style="margin-bottom: 25px;">
            <div class="form-group">
                <input type="text" name="search" class="form-input" placeholder="🔍 Поиск пользователей..." value="{search_query}">
            </div>
            <button type="submit" class="btn">🔍 Искать</button>
        </form>
        
        {users_html}
        
        <div style="margin-top: 20px;">
            <a href="/admin" class="btn">← Назад в админ-панель</a>
        </div>
    </div>
    ''')

@app.route('/admin/ban_user/<int:user_id>')
@login_required
def admin_ban_user(user_id):
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    if user_id == current_user.id:
        flash('❌ Нельзя забанить самого себя', 'error')
        return redirect('/admin/users')
    
    user = User.query.get_or_404(user_id)
    
    if user.is_banned:
        flash('❌ Пользователь уже забанен', 'error')
        return redirect('/admin/users')
    
    user.is_banned = True
    db.session.commit()
    
    flash(f'✅ Пользователь {user.username} забанен', 'success')
    return redirect('/admin/users')

@app.route('/admin/unban_user/<int:user_id>')
@login_required
def admin_unban_user(user_id):
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    user = User.query.get_or_404(user_id)
    
    if not user.is_banned:
        flash('❌ Пользователь не был забанен', 'error')
        return redirect('/admin/users')
    
    user.is_banned = False
    db.session.commit()
    
    flash(f'✅ Пользователь {user.username} разбанен', 'success')
    return redirect('/admin/users')

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def admin_delete_user(user_id):
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    if user_id == current_user.id:
        flash('❌ Нельзя удалить свой собственный аккаунт', 'error')
        return redirect('/admin/users')
    
    user = User.query.get_or_404(user_id)
    
    try:
        # Удаляем аватар пользователя
        if user.avatar_filename and user.avatar_filename != 'default_avatar.png':
            avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], user.avatar_filename)
            if os.path.exists(avatar_path):
                os.remove(avatar_path)
        
        db.session.delete(user)
        db.session.commit()
        flash(f'✅ Аккаунт пользователя {user.username} удален', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка при удалении: {str(e)}', 'error')
    
    return redirect('/admin/users')

@app.route('/admin/make_admin/<int:user_id>')
@login_required
def make_admin(user_id):
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        flash('❌ Пользователь уже является администратором', 'error')
        return redirect('/admin/users')
    
    user.is_admin = True
    db.session.commit()
    
    flash(f'✅ Пользователь {user.username} назначен администратором', 'success')
    return redirect('/admin/users')

@app.route('/admin/remove_admin/<int:user_id>')
@login_required
def remove_admin(user_id):
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    if user_id == current_user.id:
        flash('❌ Нельзя снять права администратора у самого себя', 'error')
        return redirect('/admin/users')
    
    user = User.query.get_or_404(user_id)
    
    if not user.is_admin:
        flash('❌ Пользователь не является администратором', 'error')
        return redirect('/admin/users')
    
    user.is_admin = False
    db.session.commit()
    
    flash(f'✅ Права администратора сняты с пользователя {user.username}', 'success')
    return redirect('/admin/users')

@app.route('/admin/reports')
@login_required
def admin_reports():
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    posts_with_reports = Post.query.filter(Post.reports_count > 0).all()
    comments_with_reports = Comment.query.filter(Comment.reports_count > 0).all()
    messages_with_reports = Message.query.filter(Message.reports_count > 0).all()
    
    reports_html = ''
    
    if not posts_with_reports and not comments_with_reports and not messages_with_reports:
        reports_html = '<p style="text-align: center; color: #666; padding: 40px;">Жалоб пока нет.</p>'
    else:
        for post in posts_with_reports:
            author = User.query.get(post.user_id)
            reports_html += f'''
            <div class="card" style="margin-bottom: 15px; border-left: 5px solid #dc3545;">
                <h4>📝 Жалоба на пост</h4>
                <p><strong>Автор:</strong> {author.first_name} {author.last_name} (@{author.username})</p>
                <p><strong>Содержание:</strong> {post.content[:200]}{'...' if len(post.content) > 200 else ''}</p>
                <p><strong>Количество жалоб:</strong> {post.reports_count}</p>
                <p><strong>Статус:</strong> {'🚫 Скрыт' if post.is_hidden else '👁 Видим'}</p>
                <div style="display: flex; gap: 5px; margin-top: 10px;">
                    <a href="/feed" class="btn btn-small">👁 Просмотреть пост</a>
                    <a href="/admin/delete_user/{author.id}" class="btn btn-small btn-danger">🚫 Забанить автора</a>
                    <a href="/admin/hide_post/{post.id}" class="btn btn-small btn-warning">👁 Скрыть пост</a>
                </div>
            </div>
            '''
    
    return render_page('Админ - Жалобы', f'''
    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 25px;">📊 Управление жалобами</h2>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 25px;">
            <div style="background: #f8d7da; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #dc3545;">{len(posts_with_reports)}</h3>
                <p>Жалоб на посты</p>
            </div>
            <div style="background: #fff3cd; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #856404;">{len(comments_with_reports)}</h3>
                <p>Жалоб на комментарии</p>
            </div>
            <div style="background: #d1ecf1; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #0c5460;">{len(messages_with_reports)}</h3>
                <p>Жалоб на сообщения</p>
            </div>
        </div>
        
        {reports_html}
        
        <div style="margin-top: 20px;">
            <a href="/admin" class="btn">← Назад в админ-панель</a>
        </div>
    </div>
    ''')

@app.route('/admin/hide_post/<int:post_id>')
@login_required
def admin_hide_post(post_id):
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    post = Post.query.get_or_404(post_id)
    post.is_hidden = True
    db.session.commit()
    
    flash('✅ Пост скрыт от пользователей', 'success')
    return redirect('/admin/reports')

@app.route('/admin/ads')
@login_required
def admin_ads():
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    pending_ads = Advertisement.query.filter_by(status='pending').all()
    approved_ads = Advertisement.query.filter_by(status='approved').all()
    rejected_ads = Advertisement.query.filter_by(status='rejected').all()
    
    ads_html = ''
    
    if pending_ads:
        ads_html += '<h3 style="color: #856404; margin-top: 20px;">⏳ Ожидающие модерации</h3>'
        for ad in pending_ads:
            creator = User.query.get(ad.user_id)
            ads_html += f'''
            <div class="card" style="margin-bottom: 15px; border-left: 5px solid #ffc107;">
                <h4>{ad.title}</h4>
                <p><strong>Создатель:</strong> {creator.first_name} {creator.last_name} (@{creator.username})</p>
                <p><strong>Описание:</strong> {ad.description[:200]}{'...' if len(ad.description) > 200 else ''}</p>
                <p><strong>Дата создания:</strong> {ad.created_at.strftime('%d.%m.%Y %H:%M')}</p>
                
                {f'<p><strong>Изображение:</strong> <img src="/static/uploads/{ad.image_filename}" style="max-width: 200px; max-height: 200px; border-radius: 8px;"></p>' if ad.image_filename else ''}
                
                <div style="display: flex; gap: 5px; margin-top: 10px;">
                    <a href="/admin/approve_ad/{ad.id}" class="btn btn-small btn-success">✅ Одобрить</a>
                    <a href="/admin/reject_ad/{ad.id}" class="btn btn-small btn-danger">❌ Отклонить</a>
                </div>
            </div>
            '''
    
    if not ads_html:
        ads_html = '<p style="text-align: center; color: #666; padding: 40px;">Нет рекламных предложений для модерации.</p>'
    
    return render_page('Админ - Реклама', f'''
    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 25px;">📢 Модерация рекламных предложений</h2>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 25px;">
            <div style="background: #fff3cd; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #856404;">{len(pending_ads)}</h3>
                <p>Ожидают модерации</p>
            </div>
            <div style="background: #d4edda; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #28a745;">{len(approved_ads)}</h3>
                <p>Одобрено</p>
            </div>
            <div style="background: #f8d7da; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #dc3545;">{len(rejected_ads)}</h3>
                <p>Отклонено</p>
            </div>
        </div>
        
        {ads_html}
        
        <div style="margin-top: 20px;">
            <a href="/admin" class="btn">← Назад в админ-панель</a>
        </div>
    </div>
    ''')

@app.route('/admin/approve_ad/<int:ad_id>')
@login_required
def admin_approve_ad(ad_id):
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    ad = Advertisement.query.get_or_404(ad_id)
    ad.status = 'approved'
    db.session.commit()
    
    flash('✅ Рекламное предложение одобрено', 'success')
    return redirect('/admin/ads')

@app.route('/admin/reject_ad/<int:ad_id>')
@login_required
def admin_reject_ad(ad_id):
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    ad = Advertisement.query.get_or_404(ad_id)
    ad.status = 'rejected'
    db.session.commit()
    
    flash('✅ Рекламное предложение отклонено', 'success')
    return redirect('/admin/ads')

# ========== СЛУЖЕБНЫЕ МАРШРУТЫ ==========
@app.route('/health')
def health():
    return 'OK', 200

@app.route('/init')
def init_db():
    """Инициализация базы данных"""
    try:
        db.create_all()
        return '''
        <div class="card">
            <h2 style="color: #2a5298;">✅ База данных инициализирована!</h2>
            <p>Теперь вы можете зарегистрироваться или войти в систему.</p>
            <p style="margin-top: 20px;">
                <a href="/" class="btn">🏠 На главную</a>
                <a href="/register" class="btn btn-success">📝 Зарегистрироваться</a>
            </p>
        </div>
        '''
    except Exception as e:
        return f'''
        <div class="card">
            <h2 style="color: #dc3545;">❌ Ошибка инициализации</h2>
            <p>{str(e)}</p>
        </div>
        '''

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("=" * 60)
        print("✅ MateuGram запущен!")
        print(f"🔧 База данных: {app.config['SQLALCHEMY_DATABASE_URI']}")
        print(f"📊 Пользователей в базе: {User.query.count()}")
        print(f"📝 Постов в базе: {Post.query.count()}")
        print("=" * 60)
    
    # Используем порт 8321 как вы указали
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=True)
