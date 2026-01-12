"""
MateuGram - Синяя социальная сеть
Версия с функциями редактирования профиля, загрузкой фото/видео, смайликами, подписками
"""

from flask import Flask, render_template_string, request, redirect, url_for, flash, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import re
import secrets
import os
import json
from datetime import datetime

# ========== НАСТРОЙКА ПРИЛОЖЕНИЯ ==========
app = Flask(__name__)

# Настройки приложения для Render.com
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
    
    # Подписки: кто на кого подписан
    following = db.relationship('Follow', foreign_keys='Follow.follower_id', backref='follower', lazy=True)
    followers = db.relationship('Follow', foreign_keys='Follow.followed_id', backref='followed', lazy=True)

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Кто подписался
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # На кого подписался
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('follower_id', 'followed_id', name='unique_follow'),)

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

def is_user_blocked(blocker_id, blocked_id):
    """Проверяет, заблокировал ли пользователь другого пользователя"""
    return BlockedUser.query.filter_by(blocker_id=blocker_id, blocked_id=blocked_id).first() is not None

def get_like_count(post_id):
    """Получает количество лайков поста"""
    return Like.query.filter_by(post_id=post_id).count()

def get_comment_count(post_id):
    """Получает количество комментариев поста"""
    return Comment.query.filter_by(post_id=post_id).count()

def is_following(follower_id, followed_id):
    """Проверяет, подписан ли пользователь на другого пользователя"""
    return Follow.query.filter_by(follower_id=follower_id, followed_id=followed_id).first() is not None

def get_following_count(user_id):
    """Получает количество подписок пользователя"""
    return Follow.query.filter_by(follower_id=user_id).count()

def get_followers_count(user_id):
    """Получает количество подписчиков пользователя"""
    return Follow.query.filter_by(followed_id=user_id).count()

def report_content(item_type, item_id, user_id):
    """Добавляет жалобу на контент"""
    if item_type == 'post':
        item = Post.query.get(item_id)
    elif item_type == 'message':
        item = Message.query.get(item_id)
    elif item_type == 'comment':
        item = Comment.query.get(item_id)
    else:
        return False, "Неверный тип контента"
    
    if not item:
        return False, "Контент не найден"
    
    reported_by = item.reported_by.split(',') if item.reported_by else []
    
    if str(user_id) in reported_by:
        return False, "Вы уже жаловались на этот контент"
    
    item.reports_count += 1
    if item.reported_by:
        item.reported_by += f',{user_id}'
    else:
        item.reported_by = str(user_id)
    
    if item.reports_count >= 3:
        item.is_hidden = True
    
    db.session.commit()
    
    if item.reports_count >= 3:
        return True, f"✅ Жалоба принята. Контент скрыт после {item.reports_count} жалоб."
    else:
        return True, f"✅ Жалоба принята. Всего жалоб: {item.reports_count}/3"

def get_blocked_users(user_id):
    """Получает список заблокированных пользователей"""
    blocked_records = BlockedUser.query.filter_by(blocker_id=user_id).all()
    blocked_users = []
    
    for record in blocked_records:
        user = User.query.get(record.blocked_id)
        if user:
            blocked_users.append({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'blocked_at': record.created_at
            })
    
    return blocked_users

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
        .btn-secondary {{
            background: #6c757d;
        }}
        .btn-success {{
            background: #28a745;
        }}
        .btn-warning {{
            background: #ffc107;
            color: #212529;
        }}
        .btn-danger {{
            background: #dc3545;
        }}
        .btn-admin {{
            background: #6f42c1;
        }}
        .btn-block {{
            background: #fd7e14;
        }}
        .btn-report {{
            background: #ff6b6b;
        }}
        .btn-like {{
            background: #e83e8c;
        }}
        .btn-comment {{
            background: #20c997;
        }}
        .btn-follow {{
            background: #17a2b8;
        }}
        .btn-small {{
            padding: 6px 12px;
            font-size: 14px;
        }}
        .alert {{
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 5px solid;
        }}
        .alert-success {{
            background: #d4edda;
            border-color: #28a745;
            color: #155724;
        }}
        .alert-error {{
            background: #f8d7da;
            border-color: #dc3545;
            color: #721c24;
        }}
        .alert-info {{
            background: #d1ecf1;
            border-color: #17a2b8;
            color: #0c5460;
        }}
        .alert-warning {{
            background: #fff3cd;
            border-color: #ffc107;
            color: #856404;
        }}
        .post {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.08);
            position: relative;
        }}
        .post.hidden {{
            background: #f8f9fa;
            opacity: 0.7;
        }}
        .post-header {{
            display: flex;
            align-items: center;
            margin-bottom: 15px;
        }}
        .avatar {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            object-fit: cover;
            margin-right: 12px;
            border: 2px solid #2a5298;
        }}
        .post-author {{
            font-weight: 600;
            color: #2a5298;
        }}
        .post-time {{
            color: #888;
            font-size: 0.9em;
            margin-left: auto;
        }}
        .post-content {{
            line-height: 1.6;
            margin-bottom: 15px;
        }}
        .post-actions {{
            display: flex;
            gap: 10px;
            margin-top: 15px;
            flex-wrap: wrap;
        }}
        .post-stats {{
            display: flex;
            gap: 20px;
            margin-top: 10px;
            color: #666;
            font-size: 0.9em;
        }}
        .post-stats span {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        .comments-section {{
            margin-top: 20px;
            border-top: 1px solid #eee;
            padding-top: 15px;
        }}
        .comment {{
            background: #f8f9fa;
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 10px;
            border-left: 3px solid #2a5298;
        }}
        .comment-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
            font-size: 0.9em;
            color: #666;
        }}
        .comment-content {{
            line-height: 1.4;
        }}
        .comment-actions {{
            display: flex;
            gap: 5px;
            margin-top: 8px;
        }}
        .message {{
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
            border-left: 4px solid #2a5298;
        }}
        .message.hidden {{
            background: #f1f1f1;
            opacity: 0.7;
        }}
        .message.sent {{
            background: #e3f2fd;
            border-left-color: #2196f3;
            margin-left: 50px;
        }}
        .message.received {{
            background: #f1f8e9;
            border-left-color: #4caf50;
            margin-right: 50px;
        }}
        .message-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 0.9em;
            color: #666;
        }}
        .message-content {{
            line-height: 1.5;
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
        .profile-header {{
            display: flex;
            align-items: center;
            gap: 25px;
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 2px solid #eee;
        }}
        .profile-avatar {{
            width: 150px;
            height: 150px;
            border-radius: 50%;
            object-fit: cover;
            border: 5px solid #2a5298;
        }}
        .profile-info h2 {{
            color: #2a5298;
            margin-bottom: 5px;
        }}
        .profile-info p {{
            color: #666;
            margin-bottom: 15px;
        }}
        .bio-text {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin-top: 10px;
            line-height: 1.6;
        }}
        .admin-label {{
            background: #6f42c1;
            color: white;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 12px;
            margin-left: 10px;
        }}
        .banned-label {{
            background: #dc3545;
            color: white;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 12px;
            margin-left: 10px;
        }}
        .user-list {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .user-card {{
            background: white;
            border-radius: 10px;
            padding: 15px;
            text-align: center;
            box-shadow: 0 3px 10px rgba(0,0,0,0.08);
            transition: transform 0.2s;
        }}
        .user-card:hover {{
            transform: translateY(-5px);
        }}
        .user-avatar {{
            width: 80px;
            height: 80px;
            border-radius: 50%;
            object-fit: cover;
            margin: 0 auto 10px;
            border: 3px solid #2a5298;
        }}
        .user-name {{
            font-weight: bold;
            color: #2a5298;
            margin-bottom: 5px;
        }}
        .user-bio {{
            color: #666;
            font-size: 0.9em;
            margin: 10px 0;
            line-height: 1.4;
        }}
        .nav-menu {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .nav-btn {{
            background: white;
            color: #2a5298;
            border: 2px solid #2a5298;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s;
        }}
        .nav-btn:hover {{
            background: #2a5298;
            color: white;
        }}
        .nav-btn.active {{
            background: #2a5298;
            color: white;
        }}
        .unread-badge {{
            background: #dc3545;
            color: white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            margin-left: 5px;
        }}
        .warning-badge {{
            background: #ffc107;
            color: #212529;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 12px;
            margin-left: 10px;
        }}
        .hidden-label {{
            background: #6c757d;
            color: white;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 12px;
            margin-left: 10px;
        }}
        .blocked-label {{
            background: #fd7e14;
            color: white;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 12px;
            margin-left: 10px;
        }}
        .content-warning {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px 15px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        .blocked-message {{
            background: #f8d7da;
            border: 1px solid #dc3545;
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
            text-align: center;
            color: #721c24;
        }}
        .admin-actions {{
            background: #e8e2f7;
            border: 2px solid #6f42c1;
            border-radius: 10px;
            padding: 15px;
            margin: 15px 0;
        }}
        .blocked-users-list {{
            margin-top: 20px;
        }}
        .blocked-user-item {{
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .delete-btn {{
            position: absolute;
            top: 15px;
            right: 15px;
            background: rgba(220, 53, 69, 0.1);
            color: #dc3545;
            border: none;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
        }}
        .delete-btn:hover {{
            background: rgba(220, 53, 69, 0.2);
        }}
        .follow-stats {{
            display: flex;
            gap: 20px;
            margin: 15px 0;
        }}
        .follow-stat {{
            text-align: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        .follow-stat-number {{
            font-size: 1.5em;
            font-weight: bold;
            color: #2a5298;
        }}
        .follow-stat-label {{
            font-size: 0.9em;
            color: #666;
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
        if (input) {{
            input.value += emoji;
        }}
    }}
    
    function previewMedia(input, containerId, maxFiles) {{
        const container = document.getElementById(containerId);
        if (!container) return;
        
        container.innerHTML = '';
        
        if (input.files.length > maxFiles) {{
            alert('Максимальное количество файлов: ' + maxFiles);
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
    
    function confirmReport(itemType, itemId) {{
        if (confirm('Вы уверены, что хотите пожаловаться на этот контент?\\n\\nКонтент будет скрыт после 3 жалоб.')) {{
            window.location.href = '/report/' + itemType + '/' + itemId;
        }}
    }}
    
    function confirmBlock(userId, userName) {{
        if (confirm('Вы уверены, что хотите заблокировать пользователя ' + userName + '?\\n\\nВы больше не сможете видеть его посты и сообщения.')) {{
            window.location.href = '/block_user/' + userId;
        }}
    }}
    
    function confirmUnblock(userId, userName) {{
        if (confirm('Вы уверены, что хотите разблокировать пользователя ' + userName + '?')) {{
            window.location.href = '/unblock_user/' + userId;
        }}
    }}
    
    function confirmDelete(item, id) {{
        if (confirm('Вы уверены, что хотите удалить ' + item + '?')) {{
            if (item === 'сообщение') {{
                window.location.href = '/delete_message/' + id;
            }} else if (item === 'пост') {{
                window.location.href = '/delete_post/' + id;
            }} else if (item === 'комментарий') {{
                window.location.href = '/delete_comment/' + id;
            }}
        }}
    }}
    
    function confirmBan(userId, userName) {{
        if (confirm('Вы уверены, что хотите ЗАБАНИТЬ пользователя ' + userName + '?\\n\\nОн больше не сможет заходить в систему!')) {{
            window.location.href = '/admin/ban_user/' + userId;
        }}
    }}
    
    function confirmUnban(userId, userName) {{
        if (confirm('Вы уверены, что хотите РАЗБАНИТЬ пользователя ' + userName + '?')) {{
            window.location.href = '/admin/unban_user/' + userId;
        }}
    }}
    
    function confirmDeleteAccount(userId, userName) {{
        if (confirm('⚠️ ВНИМАНИЕ! Вы уверены, что хотите УДАЛИТЬ аккаунт пользователя ' + userName + '?\\n\\nЭто действие необратимо! Все посты и сообщения пользователя будут удалены!')) {{
            window.location.href = '/admin/delete_user/' + userId;
        }}
    }}
    
    function confirmMakeAdmin(userId, userName) {{
        if (confirm('Вы уверены, что хотите назначить ' + userName + ' администратором?\\n\\nОн получит полный доступ к панели администратора.')) {{
            window.location.href = '/admin/make_admin/' + userId;
        }}
    }}
    
    function confirmRemoveAdmin(userId, userName) {{
        if (confirm('Вы уверены, что хотите снять права администратора у ' + userName + '?')) {{
            window.location.href = '/admin/remove_admin/' + userId;
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
    </div>

    <div class="card">
        <h3 style="color: #2a5298; margin-bottom: 15px;">Новые возможности:</h3>
        <ul style="list-style: none; padding: 0;">
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Подписки на пользователей</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Редактирование профиля</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Загрузка фото и видео в посты</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Смайлики в сообщениях и постах</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Админ-панель с назначением админов</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Комментарии и лайки</li>
            <li style="padding: 10px 0;">✅ Автоматическое подтверждение email</li>
        </ul>
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
        
        # Если пользователь регистрируется как MateuGram, делаем его администратором
        is_admin = (username.lower() == 'mateugram')
        
        # СОЗДАЕМ ПОЛЬЗОВАТЕЛЯ С АВТОМАТИЧЕСКИ ПОДТВЕРЖДЕННЫМ EMAIL
        new_user = User(
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            password_hash=generate_password_hash(password),
            email_verified=True,  # АВТОМАТИЧЕСКОЕ ПОДТВЕРЖДЕНИЕ
            verification_code=None,  # НЕ НУЖЕН КОД
            is_active=True,
            is_admin=is_admin
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        # АВТОМАТИЧЕСКИ ВХОДИМ ПОСЛЕ РЕГИСТРАЦИИ
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
            
            # ПРОВЕРКА EMAIL УБРАНА - ВСЕ УЖЕ ПОДТВЕРЖДЕНЫ ПРИ РЕГИСТРАЦИИ
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

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('✅ Вы вышли из системы', 'success')
    return redirect('/')

# ========== ПОДПИСКИ ==========
@app.route('/follow/<int:user_id>')
@login_required
def follow_user(user_id):
    """Подписаться на пользователя"""
    user_to_follow = User.query.get_or_404(user_id)
    
    if user_to_follow.id == current_user.id:
        flash('❌ Нельзя подписаться на самого себя', 'error')
        return redirect(f'/profile/{user_id}')
    
    # Проверяем, не заблокирован ли пользователь
    if is_user_blocked(current_user.id, user_id) or is_user_blocked(user_id, current_user.id):
        flash('🚫 Вы не можете подписаться на этого пользователя', 'error')
        return redirect(f'/profile/{user_id}')
    
    # Проверяем, не подписан ли уже
    if is_following(current_user.id, user_id):
        flash('❌ Вы уже подписаны на этого пользователя', 'error')
        return redirect(f'/profile/{user_id}')
    
    new_follow = Follow(follower_id=current_user.id, followed_id=user_id)
    db.session.add(new_follow)
    db.session.commit()
    
    flash(f'✅ Вы подписались на {user_to_follow.first_name} {user_to_follow.last_name}', 'success')
    return redirect(f'/profile/{user_id}')

@app.route('/unfollow/<int:user_id>')
@login_required
def unfollow_user(user_id):
    """Отписаться от пользователя"""
    user_to_unfollow = User.query.get_or_404(user_id)
    
    if user_to_unfollow.id == current_user.id:
        flash('❌ Нельзя отписаться от самого себя', 'error')
        return redirect(f'/profile/{user_id}')
    
    # Проверяем, подписан ли пользователь
    follow_record = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
    
    if not follow_record:
        flash('❌ Вы не подписаны на этого пользователя', 'error')
        return redirect(f'/profile/{user_id}')
    
    db.session.delete(follow_record)
    db.session.commit()
    
    flash(f'✅ Вы отписались от {user_to_unfollow.first_name} {user_to_unfollow.last_name}', 'success')
    return redirect(f'/profile/{user_id}')

@app.route('/following')
@login_required
def following():
    """Пользователи, на которых подписан текущий пользователь"""
    following_records = Follow.query.filter_by(follower_id=current_user.id).all()
    
    following_users = []
    for record in following_records:
        user = User.query.get(record.followed_id)
        if user:
            following_users.append({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'avatar': user.avatar_filename,
                'bio': user.bio[:100] if user.bio else '',
                'followed_at': record.created_at
            })
    
    users_html = ""
    for user in following_users:
        users_html += f'''<div class="user-card">
            <img src="/static/uploads/{user['avatar']}" class="user-avatar">
            <div class="user-name">{user['first_name']} {user['last_name']}</div>
            <small>@{user['username']}</small>
            <div class="user-bio">{user['bio']}{'...' if len(user['bio']) > 100 else ''}</div>
            <div style="margin-top: 10px; font-size: 0.9em; color: #666;">
                Подписан с: {user['followed_at'].strftime('%d.%m.%Y')}
            </div>
            <div style="display: flex; gap: 5px; margin-top: 10px;">
                <a href="/profile/{user['id']}" class="btn btn-small">👤 Профиль</a>
                <a href="/unfollow/{user['id']}" class="btn btn-small btn-danger">❌ Отписаться</a>
            </div>
        </div>'''
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/following" class="nav-btn active">👥 Подписки</a>
        <a href="/followers" class="nav-btn">👤 Подписчики</a>
        <a href="/profile/{current_user.id}" class="nav-btn">👤 Мой профиль</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">👥 Мои подписки ({len(following_users)})</h2>
        
        {f'<p style="color: #666; margin-bottom: 20px;">Вы подписаны на {len(following_users)} пользователей</p>' if following_users else ''}
        
        <div class="user-list">
            {users_html if users_html else '<p style="text-align: center; color: #666; padding: 40px;">Вы еще ни на кого не подписались.</p>'}
        </div>
    </div>'''
    
    return render_page('Мои подписки', content)

@app.route('/followers')
@login_required
def followers():
    """Подписчики текущего пользователя"""
    followers_records = Follow.query.filter_by(followed_id=current_user.id).all()
    
    followers_users = []
    for record in followers_records:
        user = User.query.get(record.follower_id)
        if user:
            followers_users.append({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'avatar': user.avatar_filename,
                'bio': user.bio[:100] if user.bio else '',
                'followed_at': record.created_at
            })
    
    users_html = ""
    for user in followers_users:
        users_html += f'''<div class="user-card">
            <img src="/static/uploads/{user['avatar']}" class="user-avatar">
            <div class="user-name">{user['first_name']} {user['last_name']}</div>
            <small>@{user['username']}</small>
            <div class="user-bio">{user['bio']}{'...' if len(user['bio']) > 100 else ''}</div>
            <div style="margin-top: 10px; font-size: 0.9em; color: #666;">
                Подписан с: {user['followed_at'].strftime('%d.%m.%Y')}
            </div>
            <div style="display: flex; gap: 5px; margin-top: 10px;">
                <a href="/profile/{user['id']}" class="btn btn-small">👤 Профиль</a>
                {f'<a href="/follow/{user['id']}" class="btn btn-small btn-success">➕ Подписаться</a>' if not is_following(current_user.id, user['id']) else '<span class="btn btn-small btn-secondary">✅ Вы подписаны</span>'}
            </div>
        </div>'''
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/following" class="nav-btn">👥 Подписки</a>
        <a href="/followers" class="nav-btn active">👤 Подписчики</a>
        <a href="/profile/{current_user.id}" class="nav-btn">👤 Мой профиль</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">👤 Мои подписчики ({len(followers_users)})</h2>
        
        {f'<p style="color: #666; margin-bottom: 20px;">У вас {len(followers_users)} подписчиков</p>' if followers_users else ''}
        
        <div class="user-list">
            {users_html if users_html else '<p style="text-align: center; color: #666; padding: 40px;">У вас пока нет подписчиков.</p>'}
        </div>
    </div>'''
    
    return render_page('Мои подписчики', content)

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
                    # Удаляем старый аватар если это не дефолтный
                    if user.avatar_filename != 'default_avatar.png':
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], user.avatar_filename)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    user.avatar_filename = saved_name
                    flash('✅ Аватар обновлен', 'success')
        
        db.session.commit()
        flash('✅ Профиль успешно обновлен', 'success')
        return redirect(f'/profile/{user.id}')
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/following" class="nav-btn">👥 Подписки</a>
        <a href="/followers" class="nav-btn">👤 Подписчики</a>
        <a href="/edit_profile" class="nav-btn active">✏️ Редактировать</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
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
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/following" class="nav-btn">👥 Подписки</a>
        <a href="/followers" class="nav-btn">👤 Подписчики</a>
        <a href="/create_post" class="nav-btn active">📝 Создать пост</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
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
    
    # Получаем посты от пользователей, на которых подписаны
    following_ids = [f.followed_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
    following_ids.append(current_user.id)  # Добавляем свои посты
    
    posts = Post.query.filter(
        Post.is_hidden == False,
        ~Post.user_id.in_(blocked_ids),
        Post.user_id.in_(following_ids)
    ).order_by(Post.created_at.desc()).all()
    
    posts_html = ""
    for post in posts:
        images = json.loads(post.images) if post.images else []
        videos = json.loads(post.videos) if post.videos else []
        
        media_html = ""
        if images or videos:
            media_html = '<div class="media-gallery">'
            for img in images:
                media_html += f'''<div class="gallery-item">
                    <img src="/static/uploads/{img}" style="cursor: pointer; transition: transform 0.3s; position: relative;" onclick="this.style.transform = this.style.transform === 'scale(1.5)' ? 'scale(1)' : 'scale(1.5)'; this.style.zIndex = this.style.zIndex === '100' ? '1' : '100';">
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
                <a href="/profile/{post.author.id}" class="btn btn-small btn-secondary">👤 Профиль</a>
                {f'<a href="/follow/{post.author.id}" class="btn btn-small btn-follow">➕ Подписаться</a>' if not is_following(current_user.id, post.author.id) and post.author.id != current_user.id else ''}
            </div>
            
            <div id="comment-form-{post.id}" style="display: none; margin-top: 15px;">
                <form method="POST" action="/add_comment/{post.id}">
                    <textarea name="content" id="comment-{post.id}" class="form-input" placeholder="Добавить комментарий..." style="min-height: 60px;"></textarea>
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
            
            <div class="comments-section" id="comments-{post.id}">
                {get_comments_html(post.id)}
            </div>
        </div>'''
    
    content = f'''<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2 style="color: #2a5298;">📰 Лента новостей (только подписки)</h2>
        <div>
            <a href="/create_post" class="btn">📝 Создать пост</a>
            <a href="/edit_profile" class="btn btn-secondary" style="margin-left: 10px;">👤 Профиль</a>
            <a href="/following" class="btn btn-follow" style="margin-left: 10px;">👥 Подписки</a>
            <a href="/messages" class="btn" style="margin-left: 10px;">💬 Сообщения</a>
            {f'<a href="/admin/users" class="btn" style="background: #6f42c1; margin-left: 10px;">👑 Админ</a>' if current_user.is_admin else ''}
            <a href="/logout" class="btn btn-danger" style="margin-left: 10px;">🚪 Выйти</a>
        </div>
    </div>
    
    {posts_html if posts_html else '<div class="card"><p style="text-align: center; color: #666; padding: 40px;">Лента пуста. Подпишитесь на других пользователей или создайте пост!</p></div>'}'''
    
    return render_page('Лента', content)

def get_comments_html(post_id):
    """Генерирует HTML для комментариев поста"""
    comments = Comment.query.filter_by(post_id=post_id, is_hidden=False).order_by(Comment.created_at).all()
    
    comments_html = ""
    for comment in comments:
        comments_html += f'''<div class="comment">
            <div class="comment-header">
                <span>{comment.author.first_name} {comment.author.last_name}</span>
                <span>{comment.created_at.strftime('%H:%M')}</span>
            </div>
            <div class="comment-content">{get_emoji_html(comment.content)}</div>
            <div class="comment-actions">
                <button onclick="confirmReport('comment', {comment.id})" class="btn btn-small btn-report">🚫 Пожаловаться</button>
                {f'<button onclick="confirmDelete(\'комментарий\', {comment.id})" class="btn btn-small btn-danger">🗑 Удалить</button>' if comment.user_id == current_user.id else ''}
            </div>
        </div>'''
    
    return comments_html

# ========== КОММЕНТАРИИ И ЛАЙКИ ==========
@app.route('/like_post/<int:post_id>')
@login_required
def like_post(post_id):
    """Лайкнуть/анлайкнуть пост"""
    post = Post.query.get_or_404(post_id)
    
    # Проверяем, не заблокирован ли автор поста
    if is_user_blocked(current_user.id, post.user_id):
        flash('🚫 Вы заблокировали этого пользователя', 'error')
        return redirect('/feed')
    
    # Проверяем, не лайкнул ли уже
    existing_like = Like.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    
    if existing_like:
        # Убираем лайк
        db.session.delete(existing_like)
        db.session.commit()
        flash('💔 Лайк убран', 'success')
    else:
        # Ставим лайк
        new_like = Like(post_id=post_id, user_id=current_user.id)
        db.session.add(new_like)
        db.session.commit()
        flash('❤️ Пост понравился', 'success')
    
    return redirect('/feed')

@app.route('/add_comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    """Добавить комментарий к посту"""
    post = Post.query.get_or_404(post_id)
    
    # Проверяем, не заблокирован ли автор поста
    if is_user_blocked(current_user.id, post.user_id):
        flash('🚫 Вы заблокировали этого пользователя', 'error')
        return redirect('/feed')
    
    content = request.form['content']
    
    if not content.strip():
        flash('❌ Комментарий не может быть пустым', 'error')
        return redirect('/feed')
    
    is_clean, found_words = check_content_for_report(content)
    
    if not is_clean:
        flash(f'⚠️ В вашем комментарии обнаружены слова, на которые могут пожаловаться: {", ".join(found_words)}', 'warning')
    
    new_comment = Comment(
        content=content,
        user_id=current_user.id,
        post_id=post_id
    )
    
    db.session.add(new_comment)
    db.session.commit()
    
    flash('💬 Комментарий добавлен', 'success')
    return redirect('/feed')

@app.route('/delete_comment/<int:comment_id>')
@login_required
def delete_comment(comment_id):
    """Удалить комментарий"""
    comment = Comment.query.get_or_404(comment_id)
    
    if comment.user_id != current_user.id:
        flash('❌ Вы не можете удалить этот комментарий', 'error')
        return redirect('/feed')
    
    db.session.delete(comment)
    db.session.commit()
    
    flash('✅ Комментарий удален', 'success')
    return redirect('/feed')

# ========== ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ==========
@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)
    
    if is_user_blocked(current_user.id, user_id):
        return render_page('Профиль', '<div class="card"><p style="text-align: center; color: #666; padding: 40px;">🚫 Вы заблокировали этого пользователя</p></div>')
    
    posts_count = Post.query.filter_by(user_id=user_id).count()
    followers_count = get_followers_count(user_id)
    following_count = get_following_count(user_id)
    is_following_user = is_following(current_user.id, user_id)
    
    # Получаем посты пользователя
    user_posts = Post.query.filter_by(user_id=user_id, is_hidden=False).order_by(Post.created_at.desc()).limit(10).all()
    
    posts_html = ""
    for post in user_posts:
        images = json.loads(post.images) if post.images else []
        videos = json.loads(post.videos) if post.videos else []
        
        media_html = ""
        if images or videos:
            media_html = '<div class="media-gallery">'
            for img in images[:3]:  # Показываем только первые 3 фото
                media_html += f'''<div class="gallery-item">
                    <img src="/static/uploads/{img}" style="cursor: pointer;">
                </div>'''
            for vid in videos[:1]:  # Показываем только 1 видео
                media_html += f'''<div class="gallery-item">
                    <video src="/static/uploads/{vid}" controls style="cursor: pointer;"></video>
                </div>'''
            media_html += '</div>'
        
        posts_html += f'''<div class="post">
            <div class="post-header">
                <div class="post-time">{post.created_at.strftime('%d.%m.%Y %H:%M')}</div>
            </div>
            
            <div class="post-content">{get_emoji_html(post.content)}</div>
            
            {media_html}
            
            <div class="post-stats">
                <span>❤️ {get_like_count(post.id)}</span>
                <span>💬 {get_comment_count(post.id)}</span>
            </div>
        </div>'''
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/following" class="nav-btn">👥 Подписки</a>
        <a href="/followers" class="nav-btn">👤 Подписчики</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="profile-header">
        <img src="/static/uploads/{user.avatar_filename}" class="profile-avatar">
        <div class="profile-info">
            <h2>{user.first_name} {user.last_name}</h2>
            <p>@{user.username}</p>
            <p>📧 {user.email}</p>
            <p>📅 Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}</p>
            
            <div class="follow-stats">
                <div class="follow-stat">
                    <div class="follow-stat-number">{posts_count}</div>
                    <div class="follow-stat-label">Постов</div>
                </div>
                <div class="follow-stat">
                    <div class="follow-stat-number">{followers_count}</div>
                    <div class="follow-stat-label">Подписчиков</div>
                </div>
                <div class="follow-stat">
                    <div class="follow-stat-number">{following_count}</div>
                    <div class="follow-stat-label">Подписок</div>
                </div>
            </div>
            
            {f'<div class="admin-label">👑 Администратор</div>' if user.is_admin else ''}
            {f'<div class="banned-label">🚫 Забанен</div>' if user.is_banned else ''}
            
            <div style="margin-top: 20px;">
                {f'<a href="/edit_profile" class="btn">✏️ Редактировать профиль</a>' if user_id == current_user.id else ''}
                {f'<a href="/messages/{user_id}" class="btn">💬 Написать сообщение</a>' if user_id != current_user.id else ''}
                {f'<a href="/follow/{user_id}" class="btn btn-follow">➕ Подписаться</a>' if not is_following_user and user_id != current_user.id else ''}
                {f'<a href="/unfollow/{user_id}" class="btn btn-danger">❌ Отписаться</a>' if is_following_user and user_id != current_user.id else ''}
                {f'<button onclick="confirmBlock({user_id}, \'{user.username}\')" class="btn btn-block">🚫 Заблокировать</button>' if user_id != current_user.id and not is_user_blocked(current_user.id, user_id) else ''}
                {f'<button onclick="confirmUnblock({user_id}, \'{user.username}\')" class="btn btn-warning">✅ Разблокировать</button>' if user_id != current_user.id and is_user_blocked(current_user.id, user_id) else ''}
            </div>
        </div>
    </div>
    
    <div class="card">
        <h3 style="color: #2a5298; margin-bottom: 15px;">📝 О себе</h3>
        {f'<div class="bio-text">{get_emoji_html(user.bio)}</div>' if user.bio else '<p style="color: #666; text-align: center;">Пользователь не добавил информацию о себе.</p>'}
    </div>
    
    <div class="card">
        <h3 style="color: #2a5298; margin-bottom: 15px;">📰 Последние посты</h3>
        {posts_html if posts_html else '<p style="color: #666; text-align: center;">У пользователя пока нет постов.</p>'}
    </div>'''
    
    return render_page(f'Профиль {user.username}', content)

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
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn active">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/following" class="nav-btn">👥 Подписки</a>
        <a href="/followers" class="nav-btn">👤 Подписчики</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
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

@app.route('/messages')
@login_required
def messages_list():
    """Список диалогов"""
    users = User.query.filter(User.id != current_user.id).all()
    
    users_html = ""
    for user in users:
        users_html += f'''<div class="card" style="margin-bottom: 10px;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <img src="/static/uploads/{user.avatar_filename}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;">
                    <div>
                        <div style="font-weight: 600;">{user.first_name} {user.last_name}</div>
                        <small>@{user.username}</small>
                    </div>
                </div>
                <a href="/messages/{user.id}" class="btn btn-small">💬 Написать</a>
            </div>
        </div>'''
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn active">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/following" class="nav-btn">👥 Подписки</a>
        <a href="/followers" class="nav-btn">👤 Подписчики</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">💬 Личные сообщения</h2>
        
        <div style="margin-bottom: 20px;">
            <a href="/feed" class="btn btn-secondary">← Назад в ленту</a>
        </div>
        
        <h3 style="color: #2a5298; margin-bottom: 15px;">Выберите пользователя для общения:</h3>
        
        {users_html if users_html else '<p style="text-align: center; color: #666; padding: 20px;">Нет других пользователей.</p>'}
    </div>'''
    
    return render_page('Сообщения', content)

# ========== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ==========
@app.route('/report/<item_type>/<int:item_id>')
@login_required
def report_content_route(item_type, item_id):
    """Пожаловаться на контент"""
    if item_type == 'post':
        item = Post.query.get(item_id)
    elif item_type == 'message':
        item = Message.query.get(item_id)
    elif item_type == 'comment':
        item = Comment.query.get(item_id)
    else:
        flash('Неверный тип контента', 'error')
        return redirect('/feed')
    
    if not item:
        flash('Контент не найден', 'error')
        return redirect('/feed')
    
    reported_by = item.reported_by.split(',') if item.reported_by else []
    
    if str(current_user.id) in reported_by:
        flash('Вы уже жаловались на этот контент', 'error')
        return redirect('/feed')
    
    item.reports_count += 1
    if item.reported_by:
        item.reported_by += f',{current_user.id}'
    else:
        item.reported_by = str(current_user.id)
    
    if item.reports_count >= 3:
        item.is_hidden = True
    
    db.session.commit()
    
    if item.reports_count >= 3:
        flash(f'✅ Жалоба принята. Контент скрыт после {item.reports_count} жалоб.', 'success')
    else:
        flash(f'✅ Жалоба принята. Всего жалоб: {item.reports_count}/3', 'success')
    
    return redirect('/feed')

@app.route('/block_user/<int:blocked_id>')
@login_required
def block_user(blocked_id):
    """Блокировать пользователя"""
    if current_user.id == blocked_id:
        flash('❌ Нельзя заблокировать самого себя', 'error')
        return redirect(f'/profile/{blocked_id}')
    
    if is_user_blocked(current_user.id, blocked_id):
        flash('❌ Пользователь уже заблокирован', 'error')
        return redirect(f'/profile/{blocked_id}')
    
    blocked_user = BlockedUser(blocker_id=current_user.id, blocked_id=blocked_id)
    db.session.add(blocked_user)
    db.session.commit()
    
    user = User.query.get(blocked_id)
    flash(f'✅ Пользователь {user.first_name} {user.last_name} заблокирован', 'success')
    return redirect(f'/profile/{blocked_id}')

@app.route('/unblock_user/<int:blocked_id>')
@login_required
def unblock_user(blocked_id):
    """Разблокировать пользователя"""
    blocked_record = BlockedUser.query.filter_by(blocker_id=current_user.id, blocked_id=blocked_id).first()
    
    if not blocked_record:
        flash('❌ Пользователь не был заблокирован', 'error')
        return redirect(f'/profile/{blocked_id}')
    
    db.session.delete(blocked_record)
    db.session.commit()
    
    user = User.query.get(blocked_id)
    flash(f'✅ Пользователь {user.first_name} {user.last_name} разблокирован', 'success')
    return redirect(f'/profile/{blocked_id}')

@app.route('/blocked_users')
@login_required
def blocked_users():
    """Список заблокированных пользователей"""
    blocked_users_list = get_blocked_users(current_user.id)
    
    blocked_html = ""
    if blocked_users_list:
        for blocked_user in blocked_users_list:
            blocked_html += f'''<div class="blocked-user-item">
                <div>
                    <strong>{blocked_user['first_name']} {blocked_user['last_name']}</strong><br>
                    <small>@{blocked_user['username']}</small><br>
                    <small>Заблокирован: {blocked_user['blocked_at'].strftime('%d.%m.%Y %H:%M')}</small>
                </div>
                <div>
                    <button onclick="confirmUnblock({blocked_user['id']}, '{blocked_user['username']}')" class="btn btn-warning btn-small">✅ Разблокировать</button>
                </div>
            </div>'''
    else:
        blocked_html = '<p style="text-align: center; color: #666; padding: 20px;">Вы никого не заблокировали.</p>'
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn active">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/following" class="nav-btn">👥 Подписки</a>
        <a href="/followers" class="nav-btn">👤 Подписчики</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">🚫 Заблокированные пользователи</h2>
        
        {blocked_html}
        
        <div style="margin-top: 20px;">
            <a href="/users" class="btn">👥 Посмотреть всех пользователей</a>
        </div>
    </div>'''
    
    return render_page('Заблокированные пользователи', content)

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    """Удалить пост"""
    post = Post.query.get_or_404(post_id)
    
    if post.user_id != current_user.id:
        flash('❌ Вы не можете удалить этот пост', 'error')
        return redirect('/feed')
    
    db.session.delete(post)
    db.session.commit()
    
    flash('✅ Пост удален', 'success')
    return redirect('/feed')

@app.route('/delete_message/<int:message_id>')
@login_required
def delete_message(message_id):
    """Удалить сообщение"""
    message = Message.query.get_or_404(message_id)
    
    if message.sender_id != current_user.id:
        flash('❌ Вы не можете удалить это сообщение', 'error')
        return redirect('/messages')
    
    receiver_id = message.receiver_id
    db.session.delete(message)
    db.session.commit()
    
    flash('✅ Сообщение удалено', 'success')
    return redirect(f'/messages/{receiver_id}')

@app.route('/users')
@login_required
def users():
    """Список всех пользователей"""
    search_query = request.args.get('search', '')
    
    # Получаем ID заблокированных пользователей
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
    
    users_html = ""
    if users_list:
        for user in users_list:
            users_html += f'''<div class="user-card">
                <img src="/static/uploads/{user.avatar_filename}" class="user-avatar">
                <div class="user-name">{user.first_name} {user.last_name}</div>
                <small>@{user.username}</small>
                <div class="user-bio">{user.bio[:100] if user.bio else "Пользователь пока ничего не рассказал о себе."}{'...' if user.bio and len(user.bio) > 100 else ''}</div>
                <div style="display: flex; gap: 10px; margin-top: 15px;">
                    <a href="/profile/{user.id}" class="btn btn-small">👤 Профиль</a>
                    <a href="/messages/{user.id}" class="btn btn-small btn-success">💬 Написать</a>
                    {f'<a href="/follow/{user.id}" class="btn btn-small btn-follow">➕ Подписаться</a>' if not is_following(current_user.id, user.id) else ''}
                    {f'<a href="/unfollow/{user.id}" class="btn btn-small btn-danger">❌ Отписаться</a>' if is_following(current_user.id, user.id) else ''}
                </div>
            </div>'''
    else:
        users_html = '<p style="text-align: center; color: #666; padding: 40px;">Пользователи не найдены.</p>'
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn active">👥 Все пользователи</a>
        <a href="/following" class="nav-btn">👥 Подписки</a>
        <a href="/followers" class="nav-btn">👤 Подписчики</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

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
    </div>'''
    
    return render_page('Пользователи', content)

# ========== АДМИН-ПАНЕЛЬ ==========
@app.route('/admin/users')
@login_required
def admin_users():
    """Страница управления пользователями для администратора"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
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
    
    users_html = ""
    if users_list:
        for user in users_list:
            # Подсчет постов и сообщений пользователя
            posts_count = Post.query.filter_by(user_id=user.id).count()
            messages_count = Message.query.filter_by(sender_id=user.id).count()
            
            users_html += f'''<div class="user-card">
                <img src="/static/uploads/{user.avatar_filename}" class="user-avatar">
                <div class="user-name">{user.first_name} {user.last_name}</div>
                <small>@{user.username}</small>
                <div style="margin: 10px 0;">
                    <small>Email: {user.email}</small><br>
                    <small>Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}</small><br>
                    <small>Постов: {posts_count} | Сообщений: {messages_count}</small>
                </div>
                <div style="margin: 10px 0;">
                    {f'<span class="admin-label">👑 Админ</span>' if user.is_admin else ''}
                    {f'<span class="banned-label">🚫 Забанен</span>' if user.is_banned else ''}
                    {f'<span style="color: #28a745;">✅ Активен</span>' if user.is_active and not user.is_banned else ''}
                </div>
                <div style="display: flex; gap: 5px; margin-top: 10px; flex-wrap: wrap;">
                    <a href="/profile/{user.id}" class="btn btn-small btn-secondary">👤 Профиль</a>
                    {f'<button onclick="confirmBan({user.id}, \'{user.username}\')" class="btn btn-small btn-danger">🚫 Забанить</button>' if not user.is_banned and user.id != current_user.id else ''}
                    {f'<button onclick="confirmUnban({user.id}, \'{user.username}\')" class="btn btn-small btn-success">✅ Разбанить</button>' if user.is_banned else ''}
                    {f'<button onclick="confirmDeleteAccount({user.id}, \'{user.username}\')" class="btn btn-small btn-danger">🗑 Удалить аккаунт</button>' if user.id != current_user.id else ''}
                    {f'<button onclick="confirmMakeAdmin({user.id}, \'{user.username}\')" class="btn btn-small btn-admin">👑 Назначить админом</button>' if not user.is_admin and user.id != current_user.id else ''}
                    {f'<button onclick="confirmRemoveAdmin({user.id}, \'{user.username}\')" class="btn btn-small btn-warning">👑 Снять права</button>' if user.is_admin and user.id != current_user.id else ''}
                </div>
            </div>'''
    else:
        users_html = '<p style="text-align: center; color: #666; padding: 40px;">Пользователи не найдены.</p>'
    
    # Статистика
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True, is_banned=False).count()
    banned_users = User.query.filter_by(is_banned=True).count()
    admins = User.query.filter_by(is_admin=True).count()
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/admin/users" class="nav-btn active" style="background: #6f42c1; border-color: #6f42c1;">👑 Управление пользователями</a>
        <a href="/admin/reports" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">📊 Жалобы</a>
        <a href="/admin/admins" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Администраторы</a>
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 20px;">👑 Панель администратора</h2>
        
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px;">
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
            <div style="background: #e8d6ff; padding: 15px; border-radius: 10px; text-align: center;">
                <h3 style="color: #6f42c1;">{admins}</h3>
                <p>Администраторов</p>
            </div>
        </div>
        
        <form method="GET" action="/admin/users" style="margin-bottom: 25px;">
            <div class="form-group">
                <input type="text" name="search" class="form-input" placeholder="🔍 Поиск пользователей..." value="{search_query}">
            </div>
            <button type="submit" class="btn">🔍 Искать</button>
        </form>
        
        <div class="user-list">
            {users_html}
        </div>
    </div>'''
    
    return render_page('Админ-панель - Пользователи', content)

@app.route('/admin/ban_user/<int:user_id>')
@login_required
def admin_ban_user(user_id):
    """Бан пользователя администратором"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('❌ Нельзя забанить самого себя', 'error')
        return redirect('/admin/users')
    
    if user.is_banned:
        flash(f'❌ Пользователь {user.username} уже забанен', 'error')
        return redirect('/admin/users')
    
    user.is_banned = True
    db.session.commit()
    
    flash(f'✅ Пользователь {user.username} забанен', 'success')
    return redirect('/admin/users')

@app.route('/admin/unban_user/<int:user_id>')
@login_required
def admin_unban_user(user_id):
    """Разбан пользователя администратором"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    user = User.query.get_or_404(user_id)
    
    if not user.is_banned:
        flash(f'❌ Пользователь {user.username} не забанен', 'error')
        return redirect('/admin/users')
    
    user.is_banned = False
    db.session.commit()
    
    flash(f'✅ Пользователь {user.username} разбанен', 'success')
    return redirect('/admin/users')

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def admin_delete_user(user_id):
    """Удаление аккаунта пользователя администратором"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('❌ Нельзя удалить свой собственный аккаунт', 'error')
        return redirect('/admin/users')
    
    username = user.username
    
    # Удаляем все посты пользователя
    Post.query.filter_by(user_id=user_id).delete()
    
    # Удаляем все сообщения пользователя
    Message.query.filter_by(sender_id=user_id).delete()
    Message.query.filter_by(receiver_id=user_id).delete()
    
    # Удаляем все комментарии пользователя
    Comment.query.filter_by(user_id=user_id).delete()
    
    # Удаляем все лайки пользователя
    Like.query.filter_by(user_id=user_id).delete()
    
    # Удаляем все подписки пользователя
    Follow.query.filter_by(follower_id=user_id).delete()
    Follow.query.filter_by(followed_id=user_id).delete()
    
    # Удаляем блокировки пользователя
    BlockedUser.query.filter_by(blocker_id=user_id).delete()
    BlockedUser.query.filter_by(blocked_id=user_id).delete()
    
    # Удаляем пользователя
    db.session.delete(user)
    db.session.commit()
    
    flash(f'✅ Аккаунт пользователя {username} удален', 'success')
    return redirect('/admin/users')

@app.route('/admin/make_admin/<int:user_id>')
@login_required
def make_admin(user_id):
    """Назначить пользователя администратором"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        flash(f'❌ Пользователь {user.username} уже администратор', 'error')
        return redirect('/admin/users')
    
    user.is_admin = True
    db.session.commit()
    
    flash(f'✅ Пользователь {user.username} назначен администратором', 'success')
    return redirect('/admin/users')

@app.route('/admin/remove_admin/<int:user_id>')
@login_required
def remove_admin(user_id):
    """Снять права администратора"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('❌ Нельзя снять права администратора у самого себя', 'error')
        return redirect('/admin/users')
    
    if not user.is_admin:
        flash(f'❌ Пользователь {user.username} не является администратором', 'error')
        return redirect('/admin/users')
    
    user.is_admin = False
    db.session.commit()
    
    flash(f'✅ Права администратора сняты у пользователя {user.username}', 'success')
    return redirect('/admin/users')

@app.route('/admin/admins')
@login_required
def admin_admins():
    """Управление администраторами"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    admins = User.query.filter_by(is_admin=True).all()
    
    admins_html = ""
    for admin in admins:
        posts_count = Post.query.filter_by(user_id=admin.id).count()
        comments_count = Comment.query.filter_by(user_id=admin.id).count()
        
        admins_html += f'''<div class="user-card">
            <img src="/static/uploads/{admin.avatar_filename}" class="user-avatar">
            <div class="user-name">{admin.first_name} {admin.last_name}</div>
            <small>@{admin.username}</small>
            <div style="margin: 10px 0;">
                <small>Email: {admin.email}</small><br>
                <small>Зарегистрирован: {admin.created_at.strftime('%d.%m.%Y')}</small><br>
                <small>Постов: {posts_count} | Комментариев: {comments_count}</small>
            </div>
            <div style="margin: 10px 0;">
                <span class="admin-label">👑 Администратор</span>
                {f'<span class="banned-label">🚫 Забанен</span>' if admin.is_banned else ''}
            </div>
            <div style="display: flex; gap: 5px; margin-top: 10px; flex-wrap: wrap;">
                <a href="/profile/{admin.id}" class="btn btn-small btn-secondary">👤 Профиль</a>
                {f'<button onclick="confirmRemoveAdmin({admin.id}, \'{admin.username}\')" class="btn btn-small btn-danger">👑 Снять права</button>' if admin.id != current_user.id else ''}
                {f'<button onclick="confirmBan({admin.id}, \'{admin.username}\')" class="btn btn-small btn-danger">🚫 Забанить</button>' if not admin.is_banned and admin.id != current_user.id else ''}
            </div>
        </div>'''
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Пользователи</a>
        <a href="/admin/admins" class="nav-btn active" style="background: #6f42c1; border-color: #6f42c1;">👑 Администраторы</a>
        <a href="/admin/reports" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">📊 Жалобы</a>
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 20px;">👑 Управление администраторами</h2>
        
        <div class="user-list">
            {admins_html if admins_html else '<p style="text-align: center; color: #666; padding: 40px;">Нет администраторов.</p>'}
        </div>
    </div>'''
    
    return render_page('Админ-панель - Администраторы', content)

@app.route('/admin/reports')
@login_required
def admin_reports():
    """Страница жалоб для администратора"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    # Получаем посты с жалобами
    reported_posts = Post.query.filter(Post.reports_count > 0).order_by(Post.reports_count.desc()).all()
    
    # Получаем сообщения с жалобами
    reported_messages = Message.query.filter(Message.reports_count > 0).order_by(Message.reports_count.desc()).all()
    
    # Получаем комментарии с жалобами
    reported_comments = Comment.query.filter(Comment.reports_count > 0).order_by(Comment.reports_count.desc()).all()
    
    posts_html = ""
    if reported_posts:
        for post in reported_posts:
            author = User.query.get(post.user_id)
            posts_html += f'''<div class="post{' hidden' if post.is_hidden else ''}">
                <div class="post-header">
                    <img src="/static/uploads/{author.avatar_filename}" class="avatar" style="width: 40px; height: 40px;" alt="{author.username}">
                    <div>
                        <div class="post-author">{author.first_name} {author.last_name}</div>
                        <small>@{author.username}</small>
                    </div>
                    <div class="post-time">{post.created_at.strftime('%d.%m.%Y %H:%M')}</div>
                    <span class="warning-badge">⚠️ {post.reports_count} жалоб</span>
                </div>
                <div class="post-content">{get_emoji_html(post.content)}</div>
                <div class="post-actions">
                    <a href="/profile/{author.id}" class="btn btn-small btn-secondary">👤 Профиль автора</a>
                    <button onclick="confirmBan({author.id}, '{author.username}')" class="btn btn-small btn-danger">🚫 Забанить автора</button>
                </div>
            </div>'''
    else:
        posts_html = '<p style="text-align: center; color: #666; padding: 20px;">Нет постов с жалобами.</p>'
    
    messages_html = ""
    if reported_messages:
        for msg in reported_messages:
            sender = User.query.get(msg.sender_id)
            receiver = User.query.get(msg.receiver_id)
            messages_html += f'''<div class="message{' hidden' if msg.is_hidden else ''}">
                <div class="message-header">
                    <span>От: {sender.first_name} | Кому: {receiver.first_name}</span>
                    <span>{msg.created_at.strftime('%d.%m.%Y %H:%M')}</span>
                </div>
                <div class="message-content">
                    {get_emoji_html(msg.content)}
                    <span class="warning-badge">⚠️ {msg.reports_count} жалоб</span>
                </div>
                <div style="margin-top: 10px;">
                    <a href="/profile/{sender.id}" class="btn btn-small btn-secondary">👤 Профиль отправителя</a>
                    <button onclick="confirmBan({sender.id}, '{sender.username}')" class="btn btn-small btn-danger">🚫 Забанить отправителя</button>
                </div>
            </div>'''
    else:
        messages_html = '<p style="text-align: center; color: #666; padding: 20px;">Нет сообщений с жалобами.</p>'
    
    comments_html = ""
    if reported_comments:
        for comment in reported_comments:
            author = User.query.get(comment.user_id)
            comments_html += f'''<div class="comment{' hidden' if comment.is_hidden else ''}">
                <div class="comment-header">
                    <span>{author.first_name} {author.last_name}</span>
                    <span>{comment.created_at.strftime('%d.%m.%Y %H:%M')}</span>
                </div>
                <div class="comment-content">{get_emoji_html(comment.content)}</div>
                <div class="comment-actions">
                    <a href="/profile/{author.id}" class="btn btn-small btn-secondary">👤 Профиль автора</a>
                    <button onclick="confirmBan({author.id}, '{author.username}')" class="btn btn-small btn-danger">🚫 Забанить автора</button>
                </div>
            </div>'''
    else:
        comments_html = '<p style="text-align: center; color: #666; padding: 20px;">Нет комментариев с жалобами.</p>'
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Пользователи</a>
        <a href="/admin/admins" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Администраторы</a>
        <a href="/admin/reports" class="nav-btn active" style="background: #6f42c1; border-color: #6f42c1;">📊 Жалобы</a>
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 20px;">📊 Модерация жалоб</h2>
        
        <h3 style="color: #2a5298; margin: 25px 0 15px 0;">📝 Посты с жалобами</h3>
        {posts_html}
        
        <h3 style="color: #2a5298; margin: 25px 0 15px 0;">💬 Сообщения с жалобами</h3>
        {messages_html}
        
        <h3 style="color: #2a5298; margin: 25px 0 15px 0;">💬 Комментарии с жалобами</h3>
        {comments_html}
    </div>'''
    
    return render_page('Админ-панель - Жалобы', content)

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Создаем дефолтный аватар если нужно
        default_avatar_path = os.path.join('static', 'uploads', 'default_avatar.png')
        if not os.path.exists(default_avatar_path):
            try:
                # Попробуем создать простой аватар с помощью PIL
                try:
                    from PIL import Image, ImageDraw
                    img = Image.new('RGB', (200, 200), color=(42, 82, 152))
                    d = ImageDraw.Draw(img)
                    d.ellipse([50, 50, 150, 150], fill=(255, 255, 255))
                    img.save(default_avatar_path)
                except ImportError:
                    # Если PIL нет, создаем простой текстовый файл
                    with open(default_avatar_path, 'w') as f:
                        f.write('Default Avatar')
            except:
                pass
        
        print("✅ База данных создана")
        print("🌐 Сервер запущен: http://localhost:8321")
        print("🔑 Администратор: зарегистрируйтесь с псевдонимом 'mateugram'")
        print("📧 Email автоматически подтверждается при регистрации")
    
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=True)
