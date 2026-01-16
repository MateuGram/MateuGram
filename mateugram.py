"""
MateuGram - Синяя социальная сеть
Версия с сохранением данных между перезапусками на Render.com
ПОЛНАЯ ВЕРСИЯ С ВСЕМИ МАРШРУТАМИ
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
if 'RENDER' in os.environ:
    print("🌐 Обнаружен Render.com - настраиваю устойчивое хранилище...")
    DB_FILE = '/tmp/mateugram_persistent.db'
    BACKUP_FILE = '/tmp/mateugram_backup.json'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_FILE}'
    print(f"🔧 База данных: {DB_FILE}")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mateugram.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'mkv'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

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
        
        try:
            new_user = User(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                password_hash=generate_password_hash(password),
                is_admin=False,
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
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">👤 Псевдоним</label>
                <input type="text" name="username" class="form-input" placeholder="john_doe" required>
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
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🎂 Дата рождения</label>
                <input type="date" name="birthday" class="form-input">
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🔒 Пароль</label>
                <input type="password" name="password" class="form-input" placeholder="Не менее 8 символов" required minlength="8">
            </div>
            
            <button type="submit" class="btn">📝 Создать аккаунт</button>
        </form>
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
    </div>
    ''')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('✅ Вы успешно вышли из системы', 'success')
    return redirect('/')

@app.route('/feed')
@login_required
def feed():
    try:
        # Получаем посты от пользователей, на которых подписан текущий пользователь
        following_ids = [f.followed_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
        following_ids.append(current_user.id)  # Добавляем свои посты
        
        # Блокировки
        blocked_ids = [b.blocked_id for b in BlockedUser.query.filter_by(blocker_id=current_user.id).all()]
        blocking_ids = [b.blocker_id for b in BlockedUser.query.filter_by(blocked_id=current_user.id).all()]
        
        excluded_ids = blocked_ids + blocking_ids
        
        query = Post.query.filter(
            Post.user_id.in_(following_ids),
            Post.is_hidden == False
        )
        
        if excluded_ids:
            query = query.filter(~Post.user_id.in_(excluded_ids))
        
        posts = query.order_by(Post.created_at.desc()).limit(50).all()
        
        posts_html = ''
        for post in posts:
            author = User.query.get(post.user_id)
            add_view(post.id, current_user.id)
            
            post_content = get_emoji_html(post.content)
            
            media_html = ''
            if post.images:
                images = post.images.split(',')
                media_html += '<div class="media-grid">'
                for img in images:
                    if img:
                        media_html += f'''
                        <div class="media-item">
                            <img src="/static/uploads/{img}" alt="Изображение">
                        </div>
                        '''
                media_html += '</div>'
            
            if post.videos:
                videos = post.videos.split(',')
                media_html += '<div class="media-grid">'
                for vid in videos:
                    if vid:
                        media_html += f'''
                        <div class="media-item">
                            <video controls>
                                <source src="/static/uploads/{vid}" type="video/mp4">
                            </video>
                        </div>
                        '''
                media_html += '</div>'
            
            posts_html += f'''
            <div class="post">
                <div class="post-header">
                    <div class="avatar">{author.first_name[0]}{author.last_name[0] if author.last_name else ''}</div>
                    <div>
                        <strong>{author.first_name} {author.last_name}</strong>
                        <div style="font-size: 0.9em; color: #666;">
                            @{author.username} • {post.created_at.strftime('%d.%m.%Y %H:%M')}
                        </div>
                    </div>
                </div>
                
                <p style="margin-bottom: 15px;">{post_content}</p>
                {media_html}
                
                <div style="color: #666; font-size: 0.9em; margin-top: 10px;">
                    👁️ {post.views_count} | ❤️ {get_like_count(post.id)} | 💬 {get_comment_count(post.id)}
                </div>
                
                <div class="post-actions">
                    <a href="/like/{post.id}" class="btn btn-small">❤️ Нравится</a>
                    <a href="/comment/{post.id}" class="btn btn-small">💬 Комментировать</a>
                    <a href="/profile/{author.id}" class="btn btn-small">👤 Профиль</a>
                    {f'<a href="/delete_post/{post.id}" class="btn btn-small btn-danger" onclick="confirmDeletePost({post.id})">🗑️ Удалить</a>' if current_user.id == post.user_id or current_user.is_admin else ''}
                </div>
            </div>
            '''
    except Exception as e:
        posts_html = f'<div class="alert alert-error">Ошибка загрузки ленты: {str(e)}</div>'
    
    return render_page('Лента новостей', f'''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">📰 Лента новостей</h2>
        {posts_html if posts_html else '<p style="text-align: center; color: #666;">Пока нет постов в ленте</p>'}
    </div>
    ''')

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        images = request.files.getlist('images')
        videos = request.files.getlist('videos')
        
        if not content and not images and not videos:
            flash('❌ Пост не может быть пустым', 'error')
            return redirect('/create_post')
        
        try:
            post = Post(
                content=content,
                user_id=current_user.id,
                post_type='text'
            )
            
            saved_images = []
            for img in images:
                if img and img.filename:
                    filename = save_file(img, 'image')
                    if filename:
                        saved_images.append(filename)
            
            if saved_images:
                post.images = ','.join(saved_images)
                if not content:
                    post.content = '📷 Фотографии'
                post.post_type = 'image'
            
            saved_videos = []
            for vid in videos:
                if vid and vid.filename:
                    filename = save_file(vid, 'video')
                    if filename:
                        saved_videos.append(filename)
            
            if saved_videos:
                post.videos = ','.join(saved_videos)
                if not content:
                    post.content = '🎥 Видео'
                post.post_type = 'video'
            
            db.session.add(post)
            db.session.commit()
            
            flash('✅ Пост успешно создан!', 'success')
            return redirect('/feed')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка создания поста: {str(e)}', 'error')
            return redirect('/create_post')
    
    return render_page('Создать пост', '''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">📝 Создать пост</h2>
        
        <form method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📝 Текст поста</label>
                <textarea name="content" class="form-input" rows="5" placeholder="Что у вас нового?"></textarea>
                <small style="color: #666;">Поддерживаются эмодзи: :) :( :D :P ;) :/ :O :* <3 </3</small>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📷 Фотографии (до 10)</label>
                <input type="file" name="images" class="form-input" multiple accept="image/*">
                <small style="color: #666;">PNG, JPG, JPEG, GIF</small>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🎥 Видео (до 3)</label>
                <input type="file" name="videos" class="form-input" multiple accept="video/*">
                <small style="color: #666;">MP4, MOV, AVI, MKV (до 50MB)</small>
            </div>
            
            <button type="submit" class="btn">📤 Опубликовать</button>
        </form>
    </div>
    ''')

@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    try:
        user = User.query.get_or_404(user_id)
        
        if is_user_blocked(current_user.id, user.id):
            flash('❌ Вы заблокировали этого пользователя', 'error')
            return redirect('/users')
        
        if is_user_blocked(user.id, current_user.id):
            flash('❌ Этот пользователь заблокировал вас', 'error')
            return redirect('/users')
        
        following_count = get_following_count(user.id)
        followers_count = get_followers_count(user.id)
        posts_count = Post.query.filter_by(user_id=user.id, is_hidden=False).count()
        
        posts = Post.query.filter_by(user_id=user.id, is_hidden=False).order_by(Post.created_at.desc()).limit(20).all()
        
        posts_html = ''
        for post in posts:
            post_content = get_emoji_html(post.content)
            
            media_html = ''
            if post.images:
                images = post.images.split(',')
                media_html += '<div class="media-grid">'
                for img in images[:3]:
                    if img:
                        media_html += f'<div class="media-item"><img src="/static/uploads/{img}" alt="Изображение"></div>'
                media_html += '</div>'
            
            posts_html += f'''
            <div class="post">
                <div class="post-header">
                    <div class="avatar">{user.first_name[0]}{user.last_name[0] if user.last_name else ''}</div>
                    <div>
                        <strong>{user.first_name} {user.last_name}</strong>
                        <div style="font-size: 0.9em; color: #666;">
                            @{user.username} • {post.created_at.strftime('%d.%m.%Y %H:%M')}
                        </div>
                    </div>
                </div>
                
                <p>{post_content}</p>
                {media_html}
                
                <div style="color: #666; font-size: 0.9em; margin-top: 10px;">
                    👁️ {post.views_count} | ❤️ {get_like_count(post.id)} | 💬 {get_comment_count(post.id)}
                </div>
            </div>
            '''
        
        follow_button = ''
        if user.id != current_user.id:
            if is_following(current_user.id, user.id):
                follow_button = f'''
                <a href="/unfollow/{user.id}" class="btn btn-warning">❌ Отписаться</a>
                <a href="/messages/send/{user.id}" class="btn">💬 Написать сообщение</a>
                '''
            else:
                follow_button = f'''
                <a href="/follow/{user.id}" class="btn btn-success">✅ Подписаться</a>
                <a href="/messages/send/{user.id}" class="btn">💬 Написать сообщение</a>
                '''
        
        admin_badge = '<span class="admin-badge">👑 АДМИН</span>' if user.is_admin else ''
        banned_badge = '<span class="banned-badge">🚫 ЗАБЛОКИРОВАН</span>' if user.is_banned else ''
        
        return render_page(f'Профиль {user.first_name}', f'''
        <div class="card">
            <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 20px;">
                <div class="avatar" style="width: 80px; height: 80px; font-size: 24px;">
                    {user.first_name[0]}{user.last_name[0] if user.last_name else ''}
                </div>
                <div>
                    <h2 style="color: #2a5298;">
                        {user.first_name} {user.last_name} {admin_badge} {banned_badge}
                    </h2>
                    <p style="color: #666;">@{user.username}</p>
                    <p style="margin-top: 5px;">{user.bio or 'Пользователь еще не добавил информацию о себе'}</p>
                </div>
            </div>
            
            <div class="follow-stats">
                <div class="follow-stat">
                    <div class="follow-stat-number">{posts_count}</div>
                    <div class="follow-stat-label">Постов</div>
                </div>
                <div class="follow-stat">
                    <div class="follow-stat-number">{following_count}</div>
                    <div class="follow-stat-label">Подписок</div>
                </div>
                <div class="follow-stat">
                    <div class="follow-stat-number">{followers_count}</div>
                    <div class="follow-stat-label">Подписчиков</div>
                </div>
            </div>
            
            {follow_button}
            
            {f'<a href="/admin/edit_user/{user.id}" class="btn btn-admin">✏️ Редактировать (админ)</a>' if current_user.is_admin else ''}
        </div>
        
        <div class="card">
            <h3 style="color: #2a5298; margin-bottom: 20px;">📝 Посты пользователя</h3>
            {posts_html if posts_html else '<p style="text-align: center; color: #666;">Пользователь еще не создал посты</p>'}
        </div>
        ''')
    except Exception as e:
        flash(f'❌ Ошибка загрузки профиля: {str(e)}', 'error')
        return redirect('/users')

@app.route('/users')
@login_required
def users():
    try:
        blocked_ids = [b.blocked_id for b in BlockedUser.query.filter_by(blocker_id=current_user.id).all()]
        blocking_ids = [b.blocker_id for b in BlockedUser.query.filter_by(blocked_id=current_user.id).all()]
        excluded_ids = blocked_ids + blocking_ids + [current_user.id]
        
        users_list = User.query.filter(~User.id.in_(excluded_ids), User.is_banned == False).all()
        
        users_html = ''
        for user in users_list:
            following = is_following(current_user.id, user.id)
            follow_button = f'''
            <a href="/unfollow/{user.id}" class="btn btn-small btn-warning">❌ Отписаться</a>
            ''' if following else f'''
            <a href="/follow/{user.id}" class="btn btn-small btn-success">✅ Подписаться</a>
            '''
            
            users_html += f'''
            <div class="user-card">
                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
                    <div class="avatar">{user.first_name[0]}{user.last_name[0] if user.last_name else ''}</div>
                    <div>
                        <strong>{user.first_name} {user.last_name}</strong>
                        <div style="font-size: 0.9em; color: #666;">@{user.username}</div>
                    </div>
                </div>
                <p style="font-size: 0.9em; margin-bottom: 10px;">{user.bio[:100] or 'Нет информации'}</p>
                <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                    <a href="/profile/{user.id}" class="btn btn-small">👤 Профиль</a>
                    {follow_button}
                    <a href="/messages/send/{user.id}" class="btn btn-small">💬 Сообщение</a>
                </div>
            </div>
            '''
    except Exception as e:
        users_html = f'<div class="alert alert-error">Ошибка загрузки пользователей: {str(e)}</div>'
    
    return render_page('Пользователи', f'''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">👥 Пользователи MateuGram</h2>
        <div class="user-list">
            {users_html if users_html else '<p style="grid-column: 1/-1; text-align: center; color: #666;">Нет пользователей для отображения</p>'}
        </div>
    </div>
    ''')

@app.route('/follow/<int:user_id>')
@login_required
def follow_user(user_id):
    try:
        if current_user.id == user_id:
            flash('❌ Нельзя подписаться на самого себя', 'error')
            return redirect(f'/profile/{user_id}')
        
        if is_following(current_user.id, user_id):
            flash('❌ Вы уже подписаны на этого пользователя', 'error')
            return redirect(f'/profile/{user_id}')
        
        follow = Follow(follower_id=current_user.id, followed_id=user_id)
        db.session.add(follow)
        db.session.commit()
        
        flash('✅ Вы успешно подписались на пользователя', 'success')
        return redirect(f'/profile/{user_id}')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка при подписке: {str(e)}', 'error')
        return redirect(f'/profile/{user_id}')

@app.route('/unfollow/<int:user_id>')
@login_required
def unfollow_user(user_id):
    try:
        follow = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
        if not follow:
            flash('❌ Вы не подписаны на этого пользователя', 'error')
            return redirect(f'/profile/{user_id}')
        
        db.session.delete(follow)
        db.session.commit()
        
        flash('✅ Вы отписались от пользователя', 'success')
        return redirect(f'/profile/{user_id}')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка при отписке: {str(e)}', 'error')
        return redirect(f'/profile/{user_id}')

@app.route('/like/<int:post_id>')
@login_required
def like_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        
        existing_like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
        if existing_like:
            db.session.delete(existing_like)
            flash('❤️ Вы убрали лайк', 'info')
        else:
            like = Like(user_id=current_user.id, post_id=post_id)
            db.session.add(like)
            flash('❤️ Вы поставили лайк', 'success')
        
        db.session.commit()
        return redirect('/feed')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка: {str(e)}', 'error')
        return redirect('/feed')

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        
        if current_user.id != post.user_id and not current_user.is_admin:
            flash('❌ У вас нет прав удалять этот пост', 'error')
            return redirect('/feed')
        
        db.session.delete(post)
        db.session.commit()
        
        flash('✅ Пост успешно удален', 'success')
        return redirect('/feed')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка удаления: {str(e)}', 'error')
        return redirect('/feed')

@app.route('/messages')
@login_required
def messages():
    try:
        conversations = Message.query.filter(
            (Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)
        ).order_by(Message.created_at.desc()).all()
        
        unique_users = {}
        for msg in conversations:
            other_id = msg.receiver_id if msg.sender_id == current_user.id else msg.sender_id
            if other_id not in unique_users:
                user = User.query.get(other_id)
                if user:
                    unread_count = Message.query.filter_by(
                        sender_id=other_id, 
                        receiver_id=current_user.id,
                        is_read=False
                    ).count()
                    unique_users[other_id] = {
                        'user': user,
                        'last_message': msg,
                        'unread_count': unread_count
                    }
        
        conversations_html = ''
        for data in unique_users.values():
            user = data['user']
            msg = data['last_message']
            unread = data['unread_count']
            
            conversations_html += f'''
            <div class="user-card" style="cursor: pointer; border-left: {'4px solid #2a5298' if unread > 0 else '4px solid #ddd'}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <div class="avatar" style="width: 40px; height: 40px;">
                            {user.first_name[0]}{user.last_name[0] if user.last_name else ''}
                        </div>
                        <div>
                            <strong>{user.first_name} {user.last_name}</strong>
                            <div style="font-size: 0.9em; color: #666;">@{user.username}</div>
                        </div>
                    </div>
                    <div>
                        {f'<span class="banned-badge">{unread} непрочитанных</span>' if unread > 0 else ''}
                    </div>
                </div>
                <p style="margin-top: 10px; font-size: 0.9em; color: #666;">
                    {msg.content[:50]}{'...' if len(msg.content) > 50 else ''}
                </p>
                <div style="display: flex; gap: 10px; margin-top: 10px;">
                    <a href="/messages/chat/{user.id}" class="btn btn-small">💬 Открыть чат</a>
                </div>
            </div>
            '''
    except Exception as e:
        conversations_html = f'<div class="alert alert-error">Ошибка загрузки сообщений: {str(e)}</div>'
    
    return render_page('Сообщения', f'''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">💬 Мои сообщения</h2>
        <div class="user-list">
            {conversations_html if conversations_html else '<p style="grid-column: 1/-1; text-align: center; color: #666;">Нет сообщений</p>'}
        </div>
    </div>
    ''')

@app.route('/messages/chat/<int:user_id>', methods=['GET', 'POST'])
@login_required
def chat(user_id):
    try:
        other_user = User.query.get_or_404(user_id)
        
        if current_user.id == other_user.id:
            flash('❌ Нельзя писать самому себе', 'error')
            return redirect('/messages')
        
        if is_user_blocked(current_user.id, other_user.id) or is_user_blocked(other_user.id, current_user.id):
            flash('❌ Сообщения недоступны', 'error')
            return redirect('/messages')
        
        if request.method == 'POST':
            content = request.form.get('content', '').strip()
            if content:
                message = Message(
                    content=content,
                    sender_id=current_user.id,
                    receiver_id=other_user.id
                )
                db.session.add(message)
                db.session.commit()
                flash('✅ Сообщение отправлено', 'success')
                return redirect(f'/messages/chat/{user_id}')
        
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == other_user.id)) |
            ((Message.sender_id == other_user.id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.created_at.asc()).all()
        
        messages_html = ''
        for msg in messages:
            is_sender = msg.sender_id == current_user.id
            messages_html += f'''
            <div style="margin-bottom: 15px; text-align: {'right' if is_sender else 'left'}">
                <div style="display: inline-block; max-width: 70%; padding: 10px 15px; border-radius: 15px; 
                     background: {'#2a5298' if is_sender else '#f0f0f0'}; color: {'white' if is_sender else '#333'};">
                    {get_emoji_html(msg.content)}
                </div>
                <div style="font-size: 0.8em; color: #666; margin-top: 5px;">
                    {msg.created_at.strftime('%H:%M')}
                </div>
            </div>
            '''
        
        return render_page(f'Чат с {other_user.first_name}', f'''
        <div class="card">
            <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
                <div class="avatar">{other_user.first_name[0]}{other_user.last_name[0] if other_user.last_name else ''}</div>
                <div>
                    <h3 style="color: #2a5298;">{other_user.first_name} {other_user.last_name}</h3>
                    <p style="color: #666;">@{other_user.username}</p>
                </div>
            </div>
            
            <div style="max-height: 400px; overflow-y: auto; margin-bottom: 20px; padding: 15px; background: #f9f9f9; border-radius: 10px;">
                {messages_html if messages_html else '<p style="text-align: center; color: #666;">Нет сообщений</p>'}
            </div>
            
            <form method="POST">
                <div class="form-group">
                    <textarea name="content" class="form-input" rows="3" placeholder="Введите сообщение..." required></textarea>
                </div>
                <button type="submit" class="btn">📤 Отправить</button>
            </form>
        </div>
        ''')
    except Exception as e:
        flash(f'❌ Ошибка загрузки чата: {str(e)}', 'error')
        return redirect('/messages')

@app.route('/create_ad', methods=['GET', 'POST'])
@login_required
def create_ad():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        image = request.files.get('image')
        video = request.files.get('video')
        
        if not title or not description:
            flash('❌ Заполните все обязательные поля', 'error')
            return redirect('/create_ad')
        
        try:
            ad = Advertisement(
                user_id=current_user.id,
                title=title,
                description=description,
                status='pending'
            )
            
            if image and image.filename:
                filename = save_file(image, 'image')
                if filename:
                    ad.image_filename = filename
            
            if video and video.filename:
                filename = save_file(video, 'video')
                if filename:
                    ad.video_filename = filename
            
            db.session.add(ad)
            db.session.commit()
            
            flash('✅ Реклама отправлена на модерацию!', 'success')
            return redirect('/create_ad')
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка создания рекламы: {str(e)}', 'error')
            return redirect('/create_ad')
    
    return render_page('Создать рекламу', '''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">📢 Создать рекламу</h2>
        
        <form method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📝 Заголовок</label>
                <input type="text" name="title" class="form-input" placeholder="Заголовок рекламы" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📝 Описание</label>
                <textarea name="description" class="form-input" rows="5" placeholder="Подробное описание" required></textarea>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">📷 Изображение (опционально)</label>
                <input type="file" name="image" class="form-input" accept="image/*">
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 8px; font-weight: 600;">🎥 Видео (опционально)</label>
                <input type="file" name="video" class="form-input" accept="video/*">
            </div>
            
            <div class="info-box">
                <h4 style="color: #2a5298; margin-bottom: 10px;">ℹ️ Важная информация:</h4>
                <ul style="list-style: none; padding: 0; color: #666;">
                    <li>✅ Все рекламные объявления проходят модерацию администраторами</li>
                    <li>✅ Реклама появится в ленте только после одобрения</li>
                    <li>✅ Запрещена реклама запрещенных товаров и услуг</li>
                </ul>
            </div>
            
            <button type="submit" class="btn">📤 Отправить на модерацию</button>
        </form>
    </div>
    ''')

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('❌ У вас нет прав администратора', 'error')
        return redirect('/')
    
    try:
        total_users = User.query.count()
        total_posts = Post.query.count()
        total_comments = Comment.query.count()
        total_messages = Message.query.count()
        pending_ads = Advertisement.query.filter_by(status='pending').count()
        banned_users = User.query.filter_by(is_banned=True).count()
        
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_posts = Post.query.order_by(Post.created_at.desc()).limit(5).all()
        
        recent_users_html = ''
        for user in recent_users:
            recent_users_html += f'''
            <tr>
                <td>{user.id}</td>
                <td>{user.username}</td>
                <td>{user.first_name} {user.last_name}</td>
                <td>{'👑' if user.is_admin else '👤'}</td>
                <td>{'🚫' if user.is_banned else '✅'}</td>
                <td><a href="/profile/{user.id}" class="btn btn-small">👀</a></td>
            </tr>
            '''
        
        recent_posts_html = ''
        for post in recent_posts:
            author = User.query.get(post.user_id)
            recent_posts_html += f'''
            <tr>
                <td>{post.id}</td>
                <td>{post.content[:30]}...</td>
                <td>{author.username}</td>
                <td>{'✅' if not post.is_hidden else '🚫'}</td>
                <td><a href="/delete_post/{post.id}" class="btn btn-small btn-danger">🗑️</a></td>
            </tr>
            '''
    except Exception as e:
        flash(f'❌ Ошибка загрузки статистики: {str(e)}', 'error')
        return redirect('/')
    
    return render_page('Админ-панель', f'''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">👑 Административная панель</h2>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px;">
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: #2a5298;">{total_users}</div>
                <div>👥 Пользователей</div>
            </div>
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: #2a5298;">{total_posts}</div>
                <div>📝 Постов</div>
            </div>
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: #2a5298;">{total_comments}</div>
                <div>💬 Комментариев</div>
            </div>
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center;">
                <div style="font-size: 2em; font-weight: bold; color: #2a5298;">{pending_ads}</div>
                <div>📢 Ожидает модерации</div>
            </div>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div>
                <h3 style="color: #2a5298; margin-bottom: 15px;">🆕 Последние пользователи</h3>
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background: #f8f9fa;">
                                <th style="padding: 10px; text-align: left;">ID</th>
                                <th style="padding: 10px; text-align: left;">Логин</th>
                                <th style="padding: 10px; text-align: left;">Имя</th>
                                <th style="padding: 10px; text-align: left;">Роль</th>
                                <th style="padding: 10px; text-align: left;">Статус</th>
                                <th style="padding: 10px; text-align: left;">Действия</th>
                            </tr>
                        </thead>
                        <tbody>
                            {recent_users_html}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div>
                <h3 style="color: #2a5298; margin-bottom: 15px;">🆕 Последние посты</h3>
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background: #f8f9fa;">
                                <th style="padding: 10px; text-align: left;">ID</th>
                                <th style="padding: 10px; text-align: left;">Содержание</th>
                                <th style="padding: 10px; text-align: left;">Автор</th>
                                <th style="padding: 10px; text-align: left;">Статус</th>
                                <th style="padding: 10px; text-align: left;">Действия</th>
                            </tr>
                        </thead>
                        <tbody>
                            {recent_posts_html}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <div style="margin-top: 30px;">
            <h3 style="color: #2a5298; margin-bottom: 15px;">⚙️ Быстрые действия</h3>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <a href="/admin/users" class="btn">👥 Управление пользователями</a>
                <a href="/admin/posts" class="btn">📝 Управление постами</a>
                <a href="/admin/ads" class="btn">📢 Модерация рекламы</a>
                <a href="/admin/reports" class="btn">⚠️ Жалобы</a>
            </div>
        </div>
    </div>
    ''')

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('❌ У вас нет прав администратора', 'error')
        return redirect('/')
    
    try:
        users = User.query.all()
        users_html = ''
        for user in users:
            badges = ''
            if user.is_admin:
                badges += ' <span class="admin-badge">👑 АДМИН</span>'
            if user.is_banned:
                badges += ' <span class="banned-badge">🚫 ЗАБЛОКИРОВАН</span>'
            
            actions = ''
            if not user.is_admin:  # Нельзя изменять администраторов
                if user.is_banned:
                    actions += f'<a href="/admin/unban_user/{user.id}" class="btn btn-small btn-success">✅ Разблокировать</a>'
                else:
                    actions += f'<a href="/admin/ban_user/{user.id}" class="btn btn-small btn-danger">🚫 Заблокировать</a>'
                
                actions += f'<a href="/admin/make_admin/{user.id}" class="btn btn-small btn-admin">👑 Назначить админом</a>'
                actions += f'<a href="/admin/delete_user/{user.id}" class="btn btn-small btn-danger" onclick="return confirm(\'Удалить пользователя?\')">🗑️ Удалить</a>'
            
            users_html += f'''
            <tr>
                <td>{user.id}</td>
                <td>{user.username}</td>
                <td>{user.first_name} {user.last_name}</td>
                <td>{user.email}</td>
                <td>{user.created_at.strftime('%d.%m.%Y')}</td>
                <td>{badges}</td>
                <td>
                    <div style="display: flex; gap: 5px; flex-wrap: wrap;">
                        {actions}
                    </div>
                </td>
            </tr>
            '''
    except Exception as e:
        users_html = f'<tr><td colspan="7" style="text-align: center; color: red;">Ошибка: {str(e)}</td></tr>'
    
    return render_page('Управление пользователями', f'''
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">👥 Управление пользователями</h2>
        
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: #f8f9fa;">
                        <th style="padding: 12px; text-align: left;">ID</th>
                        <th style="padding: 12px; text-align: left;">Логин</th>
                        <th style="padding: 12px; text-align: left;">Имя</th>
                        <th style="padding: 12px; text-align: left;">Email</th>
                        <th style="padding: 12px; text-align: left;">Регистрация</th>
                        <th style="padding: 12px; text-align: left;">Статус</th>
                        <th style="padding: 12px; text-align: left;">Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {users_html}
                </tbody>
            </table>
        </div>
    </div>
    ''')

@app.route('/admin/ban_user/<int:user_id>')
@login_required
def ban_user(user_id):
    if not current_user.is_admin:
        flash('❌ У вас нет прав администратора', 'error')
        return redirect('/')
    
    try:
        user = User.query.get_or_404(user_id)
        if user.is_admin:
            flash('❌ Нельзя заблокировать администратора', 'error')
            return redirect('/admin/users')
        
        user.is_banned = True
        db.session.commit()
        flash(f'✅ Пользователь {user.username} заблокирован', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка: {str(e)}', 'error')
    
    return redirect('/admin/users')

@app.route('/admin/unban_user/<int:user_id>')
@login_required
def unban_user(user_id):
    if not current_user.is_admin:
        flash('❌ У вас нет прав администратора', 'error')
        return redirect('/')
    
    try:
        user = User.query.get_or_404(user_id)
        user.is_banned = False
        db.session.commit()
        flash(f'✅ Пользователь {user.username} разблокирован', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка: {str(e)}', 'error')
    
    return redirect('/admin/users')

@app.route('/admin/make_admin/<int:user_id>')
@login_required
def make_admin(user_id):
    if not current_user.is_admin:
        flash('❌ У вас нет прав администратора', 'error')
        return redirect('/')
    
    try:
        user = User.query.get_or_404(user_id)
        user.is_admin = True
        db.session.commit()
        flash(f'✅ Пользователь {user.username} назначен администратором', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка: {str(e)}', 'error')
    
    return redirect('/admin/users')

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('❌ У вас нет прав администратора', 'error')
        return redirect('/')
    
    try:
        user = User.query.get_or_404(user_id)
        if user.is_admin:
            flash('❌ Нельзя удалить администратора', 'error')
            return redirect('/admin/users')
        
        db.session.delete(user)
        db.session.commit()
        flash(f'✅ Пользователь {user.username} удален', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка: {str(e)}', 'error')
    
    return redirect('/admin/users')

@app.route('/comment/<int:post_id>', methods=['GET', 'POST'])
@login_required
def comment_post(post_id):
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if content:
            try:
                comment = Comment(
                    content=content,
                    user_id=current_user.id,
                    post_id=post_id
                )
                db.session.add(comment)
                db.session.commit()
                flash('✅ Комментарий добавлен', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'❌ Ошибка: {str(e)}', 'error')
        
        return redirect('/feed')
    
    return redirect('/feed')

@app.route('/delete_comment/<int:comment_id>')
@login_required
def delete_comment(comment_id):
    try:
        comment = Comment.query.get_or_404(comment_id)
        
        if current_user.id != comment.user_id and not current_user.is_admin:
            flash('❌ У вас нет прав удалять этот комментарий', 'error')
            return redirect('/feed')
        
        db.session.delete(comment)
        db.session.commit()
        
        flash('✅ Комментарий удален', 'success')
        return redirect('/feed')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка удаления: {str(e)}', 'error')
        return redirect('/feed')

def initialize_first_admin():
    """Создает первого администратора при первом запуске"""
    with app.app_context():
        try:
            if User.query.count() == 0:
                print("👑 Первый запуск - создание первого администратора...")
                
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
            elif User.query.filter_by(is_admin=True).first():
                print("✅ Администраторы найдены")
            else:
                print("ℹ️ В системе есть пользователи, но нет администраторов")
        except Exception as e:
            print(f"❌ Ошибка при инициализации: {e}")

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            initialize_first_admin()
            
            total_users = User.query.count()
            total_admins = User.query.filter_by(is_admin=True).count()
            total_posts = Post.query.count()
            
            print("=" * 60)
            print("✅ MateuGram запущен!")
            print(f"📊 Пользователей: {total_users}")
            print(f"👑 Администраторов: {total_admins}")
            print(f"📝 Постов: {total_posts}")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ Ошибка при запуске: {e}")
            import traceback
            traceback.print_exc()
    
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=True)
