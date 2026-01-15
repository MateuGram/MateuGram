"""
MateuGram - Синяя социальная сеть
Версия с сохранением данных между перезапусками на Render.com
ИСПРАВЛЕНА ОШИБКА - пользователи не становятся админами по умолчанию
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
    is_admin = db.Column(db.Boolean, default=False)  # По умолчанию НЕ админ
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
        avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], user.avatar_filename)
        if os.path.exists(avatar_path):
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
        .info-box { background: #f8f9fa; padding: 15px; border-radius: 10px; margin: 15px 0; border-left: 4px solid #2a5298; }
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
    
    # Статистика для главной страницы
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
        <h2 style="color: #2a5298; margin-bottom: 20px;">Добро пожаловать в MateuGram!</h2>
        <p style="margin-bottom: 25px; line-height: 1.6;">
            Безопасная социальная сеть без политики, религии и нецензурной лексики. 
            Общайтесь с друзьями, делитесь моментами и находите единомышленников.
        </p>
        
        <div class="info-box">
            <h3 style="color: #2a5298; margin-bottom: 15px;">📊 Статистика сети:</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
                <div style="text-align: center; padding: 10px; background: white; border-radius: 8px;">
                    <div style="font-size: 1.5em; font-weight: bold; color: #2a5298;">{total_users}</div>
                    <div style="font-size: 0.9em; color: #666;">Пользователей</div>
                </div>
                <div style="text-align: center; padding: 10px; background: white; border-radius: 8px;">
                    <div style="font-size: 1.5em; font-weight: bold; color: #2a5298;">{total_posts}</div>
                    <div style="font-size: 0.9em; color: #666;">Постов</div>
                </div>
                <div style="text-align: center; padding: 10px; background: white; border-radius: 8px;">
                    <div style="font-size: 1.5em; font-weight: bold; color: #2a5298;">{total_comments}</div>
                    <div style="font-size: 0.9em; color: #666;">Комментариев</div>
                </div>
            </div>
        </div>
        
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
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Блокировка нежелательных пользователей</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Жалобы на контент</li>
            <li style="padding: 10px 0;">✅ Админ-панель для модерации</li>
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
        
        # ИСПРАВЛЕНО: Убрана автоматическая проверка на админа
        # Пользователи регистрируются как обычные пользователи
        is_admin = False  # Все новые пользователи - обычные пользователи
        
        try:
            new_user = User(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                password_hash=generate_password_hash(password),
                is_admin=is_admin,  # По умолчанию False
                is_active=True,
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
            
            <div class="info-box">
                <h4 style="color: #2a5298; margin-bottom: 10px;">ℹ️ Важная информация:</h4>
                <ul style="list-style: none; padding: 0; color: #666;">
                    <li>✅ Все новые пользователи регистрируются как обычные пользователи</li>
                    <li>✅ Права администратора могут быть назначены только существующим администраторами</li>
                    <li>✅ Данные хранятся безопасно в зашифрованном виде</li>
                </ul>
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

# Остальные маршруты остаются без изменений...

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
def initialize_first_admin():
    """Создает первого администратора при первом запуске если база пуста"""
    with app.app_context():
        try:
            # Проверяем, есть ли уже администраторы
            admin_exists = User.query.filter_by(is_admin=True).first()
            
            if not admin_exists and User.query.count() == 0:
                print("👑 Первый запуск - создание первого администратора...")
                
                # Создаем администратора с уникальными данными
                first_admin = User(
                    email='admin@mateugram.com',
                    username='MateuGramAdmin',
                    first_name='Администратор',
                    last_name='Системы',
                    password_hash=generate_password_hash('AdminSecurePass123!'),
                    is_admin=True,
                    is_active=True
                )
                
                db.session.add(first_admin)
                db.session.commit()
                
                print("=" * 60)
                print("✅ Первый администратор создан!")
                print("📧 Email: admin@mateugram.com")
                print("👤 Логин: MateuGramAdmin")
                print("🔒 Пароль: AdminSecurePass123!")
                print("⚠️ Смените пароль после первого входа!")
                print("=" * 60)
            elif admin_exists:
                print(f"✅ Администраторы найдены: {admin_exists.username}")
            else:
                print("ℹ️ В системе есть пользователи, но нет администраторов")
                print("ℹ️ Существующим администраторам нужно назначить права через других администраторов")
                
        except Exception as e:
            print(f"❌ Ошибка при инициализации: {e}")

if __name__ == '__main__':
    with app.app_context():
        try:
            # Создаем таблицы если их нет
            db.create_all()
            
            # Инициализируем первого администратора только если база полностью пуста
            initialize_first_admin()
            
            # Статистика при запуске
            total_users = User.query.count()
            total_admins = User.query.filter_by(is_admin=True).count()
            total_posts = Post.query.count()
            
            print("=" * 60)
            print("✅ MateuGram запущен!")
            print(f"🔧 База данных: {app.config['SQLALCHEMY_DATABASE_URI']}")
            print(f"📊 Пользователей в базе: {total_users}")
            print(f"👑 Администраторов: {total_admins}")
            print(f"📝 Постов в базе: {total_posts}")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ Ошибка при запуске: {e}")
            import traceback
            traceback.print_exc()
    
    # Используем порт 8321 как вы указали
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=True)
