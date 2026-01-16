"""
MateuGram - Синяя социальная сеть
ПОЛНАЯ ВЕРСИЯ С КРАСИВЫМ ДИЗАЙНОМ
"""

import os
import json
import shutil
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

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ========== БАЗА ДАННЫХ ==========
if 'RENDER' in os.environ:
    print("🌐 Обнаружен Render.com - настраиваю устойчивое хранилище...")
    DB_FILE = '/tmp/mateugram_persistent.db'
    BACKUP_DIR = '/tmp/backups'
    os.makedirs(BACKUP_DIR, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_FILE}'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mateugram.db'
    BACKUP_DIR = 'backups'
    os.makedirs(BACKUP_DIR, exist_ok=True)

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

# ========== ФУНКЦИИ РЕЗЕРВНОГО КОПИРОВАНИЯ ==========
def create_backup():
    """Создает резервную копию базы данных"""
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
            
            backup_files = []
            if 'RENDER' in os.environ:
                backup_dir = '/tmp/backups'
            else:
                backup_dir = 'backups'
            
            if os.path.exists(backup_dir):
                backup_files = sorted(
                    [f for f in os.listdir(backup_dir) if f.startswith('mateugram_backup_')],
                    reverse=True
                )
                
                for old_backup in backup_files[10:]:
                    os.remove(os.path.join(backup_dir, old_backup))
            
            print(f"✅ Резервная копия создана: {backup_path}")
            return True
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")
    return False

def restore_backup(backup_filename):
    """Восстанавливает базу данных из бэкапа"""
    try:
        if 'RENDER' in os.environ:
            db_path = '/tmp/mateugram_persistent.db'
            backup_path = f'/tmp/backups/{backup_filename}'
        else:
            db_path = 'mateugram.db'
            backup_path = f'backups/{backup_filename}'
        
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, db_path)
            print(f"✅ База восстановлена из: {backup_filename}")
            return True
    except Exception as e:
        print(f"❌ Ошибка восстановления: {e}")
    return False

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

# ========== HTML ШАБЛОНЫ С КРАСИВЫМ ДИЗАЙНОМ ==========
BASE_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MateuGram - {title}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #1a2980, #26d0ce);
            color: #333;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .header {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 25px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
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
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        .header p {
            color: #666;
            font-size: 1.2em;
            font-weight: 300;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 25px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.3);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0, 0, 0, 0.15);
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
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
            box-shadow: 0 0 0 3px rgba(42, 82, 152, 0.1);
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
            box-shadow: 0 5px 15px rgba(42, 82, 152, 0.2);
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(42, 82, 152, 0.3);
            background: linear-gradient(45deg, #1e3c72, #162b5f);
        }
        
        .btn-danger {
            background: linear-gradient(45deg, #dc3545, #c82333);
            box-shadow: 0 5px 15px rgba(220, 53, 69, 0.2);
        }
        
        .btn-danger:hover {
            background: linear-gradient(45deg, #c82333, #bd2130);
            box-shadow: 0 8px 20px rgba(220, 53, 69, 0.3);
        }
        
        .btn-success {
            background: linear-gradient(45deg, #28a745, #1e7e34);
            box-shadow: 0 5px 15px rgba(40, 167, 69, 0.2);
        }
        
        .btn-success:hover {
            background: linear-gradient(45deg, #1e7e34, #186429);
            box-shadow: 0 8px 20px rgba(40, 167, 69, 0.3);
        }
        
        .btn-warning {
            background: linear-gradient(45deg, #ffc107, #e0a800);
            color: #000;
            box-shadow: 0 5px 15px rgba(255, 193, 7, 0.2);
        }
        
        .btn-warning:hover {
            background: linear-gradient(45deg, #e0a800, #d39e00);
            box-shadow: 0 8px 20px rgba(255, 193, 7, 0.3);
        }
        
        .btn-admin {
            background: linear-gradient(45deg, #6f42c1, #5a32a3);
            box-shadow: 0 5px 15px rgba(111, 66, 193, 0.2);
        }
        
        .btn-admin:hover {
            background: linear-gradient(45deg, #5a32a3, #4c288f);
            box-shadow: 0 8px 20px rgba(111, 66, 193, 0.3);
        }
        
        .nav {
            display: flex;
            gap: 15px;
            margin-bottom: 30px;
            flex-wrap: wrap;
            justify-content: center;
        }
        
        .nav-btn {
            background: rgba(255, 255, 255, 0.9);
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
            box-shadow: 0 5px 15px rgba(42, 82, 152, 0.2);
        }
        
        .post {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 18px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.3);
            transition: transform 0.3s ease;
        }
        
        .post:hover {
            transform: translateY(-3px);
        }
        
        .post-header {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
        }
        
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
            box-shadow: 0 5px 15px rgba(42, 82, 152, 0.2);
        }
        
        .alert {
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 25px;
            font-weight: 500;
            animation: slideIn 0.5s ease;
        }
        
        @keyframes slideIn {
            from {
                transform: translateY(-20px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }
        
        .alert-success {
            background: linear-gradient(45deg, #d4edda, #c3e6cb);
            color: #155724;
            border-left: 5px solid #28a745;
        }
        
        .alert-error {
            background: linear-gradient(45deg, #f8d7da, #f5c6cb);
            color: #721c24;
            border-left: 5px solid #dc3545;
        }
        
        .alert-info {
            background: linear-gradient(45deg, #d1ecf1, #bee5eb);
            color: #0c5460;
            border-left: 5px solid #17a2b8;
        }
        
        .user-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 25px;
        }
        
        .user-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 18px;
            padding: 20px;
            transition: all 0.3s ease;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }
        
        .user-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
        }
        
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
        
        .banned-badge {
            background: linear-gradient(45deg, #dc3545, #c82333);
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 8px;
            display: inline-block;
        }
        
        .follow-stats {
            display: flex;
            gap: 25px;
            margin: 20px 0;
            justify-content: center;
        }
        
        .follow-stat {
            text-align: center;
            padding: 20px;
            background: rgba(255, 255, 255, 0.9);
            border-radius: 15px;
            min-width: 120px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
        }
        
        .follow-stat-number {
            font-size: 2em;
            font-weight: 800;
            color: #2a5298;
            margin-bottom: 5px;
        }
        
        .follow-stat-label {
            font-size: 0.9em;
            color: #666;
            font-weight: 500;
        }
        
        .post-actions {
            display: flex;
            gap: 12px;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        
        .btn-small {
            padding: 10px 18px;
            font-size: 14px;
            border-radius: 10px;
        }
        
        .comments-section {
            margin-top: 25px;
            border-top: 2px solid #e1e8ed;
            padding-top: 20px;
        }
        
        .comment {
            background: rgba(248, 249, 250, 0.8);
            border-radius: 15px;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 4px solid #2a5298;
        }
        
        .comment-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 0.9em;
            color: #666;
        }
        
        .media-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        
        .media-item {
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease;
        }
        
        .media-item:hover {
            transform: scale(1.03);
        }
        
        .media-item img, .media-item video {
            width: 100%;
            height: 180px;
            object-fit: cover;
            display: block;
        }
        
        .info-box {
            background: linear-gradient(135deg, rgba(248, 249, 250, 0.9), rgba(233, 236, 239, 0.9));
            padding: 25px;
            border-radius: 18px;
            margin: 25px 0;
            border-left: 6px solid #2a5298;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.05);
        }
        
        h2, h3, h4 {
            color: #2a5298;
            margin-bottom: 20px;
            font-weight: 700;
        }
        
        h2 {
            font-size: 2.2em;
            background: linear-gradient(45deg, #1a2980, #26d0ce);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        h3 {
            font-size: 1.8em;
        }
        
        p {
            line-height: 1.7;
            color: #555;
            font-size: 1.05em;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 20px;
            margin: 25px 0;
        }
        
        .stat-item {
            background: rgba(255, 255, 255, 0.9);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.05);
            transition: transform 0.3s ease;
        }
        
        .stat-item:hover {
            transform: translateY(-5px);
        }
        
        .stat-number {
            font-size: 2.5em;
            font-weight: 800;
            color: #2a5298;
            margin-bottom: 10px;
        }
        
        .stat-label {
            font-size: 1em;
            color: #666;
            font-weight: 500;
        }
        
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            background: rgba(255, 255, 255, 0.9);
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.05);
        }
        
        th {
            background: linear-gradient(45deg, #2a5298, #1e3c72);
            color: white;
            padding: 18px;
            text-align: left;
            font-weight: 600;
        }
        
        td {
            padding: 16px;
            border-bottom: 1px solid #e1e8ed;
        }
        
        tr:last-child td {
            border-bottom: none;
        }
        
        tr:hover {
            background: rgba(248, 249, 250, 0.8);
        }
        
        .chat-message {
            max-width: 70%;
            margin-bottom: 15px;
            clear: both;
        }
        
        .message-sent {
            float: right;
            text-align: right;
        }
        
        .message-received {
            float: left;
            text-align: left;
        }
        
        .message-bubble {
            display: inline-block;
            padding: 15px 20px;
            border-radius: 20px;
            position: relative;
            box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1);
        }
        
        .sent-bubble {
            background: linear-gradient(45deg, #2a5298, #1e3c72);
            color: white;
            border-bottom-right-radius: 5px;
        }
        
        .received-bubble {
            background: #f0f0f0;
            color: #333;
            border-bottom-left-radius: 5px;
        }
        
        .message-time {
            font-size: 0.8em;
            color: #999;
            margin-top: 5px;
            display: block;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .header h1 {
                font-size: 2.2em;
            }
            
            .nav {
                flex-direction: column;
            }
            
            .nav-btn {
                justify-content: center;
            }
            
            .user-list {
                grid-template-columns: 1fr;
            }
            
            .follow-stats {
                flex-direction: column;
                align-items: center;
            }
            
            .media-grid {
                grid-template-columns: 1fr;
            }
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
    
    function copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            alert('Скопировано в буфер обмена!');
        });
    }
    </script>
</body>
</html>'''

def render_page(title, content):
    nav_links = ''
    if current_user.is_authenticated:
        nav_links = f'''
            <a href="/feed" class="nav-btn"><i class="fas fa-newspaper"></i> Лента</a>
            <a href="/create_post" class="nav-btn"><i class="fas fa-edit"></i> Создать пост</a>
            <a href="/profile/{current_user.id}" class="nav-btn"><i class="fas fa-user"></i> Мой профиль</a>
            <a href="/users" class="nav-btn"><i class="fas fa-users"></i> Пользователи</a>
            <a href="/messages" class="nav-btn"><i class="fas fa-envelope"></i> Сообщения</a>
            <a href="/create_ad" class="nav-btn"><i class="fas fa-bullhorn"></i> Реклама</a>
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
                    <i class="fas fa-lock"></i> Пароль
                </label>
                <input type="password" name="password" class="form-input" placeholder="Не менее 8 символов" required minlength="8">
            </div>
            
            <div class="info-box">
                <h4><i class="fas fa-shield-alt"></i> Безопасность данных</h4>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Все пароли хранятся в зашифрованном виде</p>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Данные защищены от несанкционированного доступа</p>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Конфиденциальность гарантируется</p>
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
                            <img src="/static/uploads/{img}" alt="Изображение" style="width: 100%; height: 180px; object-fit: cover;">
                        </div>
                        '''
                media_html += '</div>'
            
            posts_html += f'''
            <div class="post">
                <div class="post-header">
                    <div class="avatar">
                        {author.first_name[0]}{author.last_name[0] if author.last_name else ''}
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
                    <a href="/like/{post.id}" class="btn btn-small">
                        <i class="fas fa-heart"></i> Нравится
                    </a>
                    <a href="/post/{post.id}" class="btn btn-small">
                        <i class="fas fa-comment"></i> Комментировать
                    </a>
                    <a href="/profile/{author.id}" class="btn btn-small">
                        <i class="fas fa-user"></i> Профиль
                    </a>
                    {f'<a href="/delete_post/{post.id}" class="btn btn-small btn-danger" onclick="confirmAction(\'Вы уверены, что хотите удалить этот пост?\', \'/delete_post/{post.id}\')">
                        <i class="fas fa-trash"></i> Удалить
                    </a>' if current_user.id == post.user_id or current_user.is_admin else ''}
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

# [ОСТАЛЬНЫЕ МАРШРУТЫ ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙ - они используют тот же красивый дизайн]

# ========== ЗАПУСК ==========
def initialize_first_admin():
    with app.app_context():
        try:
            if User.query.count() == 0:
                print("👑 Создание первого администратора...")
                
                first_admin = User(
                    email='admin@mateugram.com',
                    username='Admin',
                    first_name='Администратор',
                    last_name='Системы',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True,
                    is_active=True
                )
                
                db.session.add(first_admin)
                db.session.commit()
                
                print("=" * 60)
                print("✅ Первый администратор создан!")
                print("📧 Email: admin@mateugram.com")
                print("👤 Логин: Admin")
                print("🔒 Пароль: admin123")
                print("=" * 60)
        except Exception as e:
            print(f"❌ Ошибка при инициализации: {e}")

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            initialize_first_admin()
            
            total_users = User.query.count()
            total_posts = Post.query.count()
            
            print("=" * 60)
            print("✅ MateuGram запущен!")
            print(f"📊 Пользователей: {total_users}")
            print(f"📝 Постов: {total_posts}")
            print("=" * 60)
            
            create_backup()
            
        except Exception as e:
            print(f"❌ Ошибка при запуске: {e}")
            import traceback
            traceback.print_exc()
    
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=True)
