"""
MateuGram - Синяя социальная сеть
ПОЛНАЯ ВЕРСИЯ С КРАСИВЫМ ДИЗАЙНОМ
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
            if not author or author.is_banned:
                continue
                
            add_view(post.id, current_user.id)
            
            post_content = get_emoji_html(post.content)
            
            media_html = ''
            if post.images:
                images = post.images.split(',')
                if any(images):
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
                    {f'<a href="/delete_post/{post.id}" class="btn btn-small btn-danger" onclick="return confirm(\'Вы уверены, что хотите удалить этот пост?\')">
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

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        
        if not content:
            flash('❌ Пост не может быть пустым', 'error')
            return redirect('/create_post')
        
        images = []
        videos = []
        
        if 'images' in request.files:
            for file in request.files.getlist('images'):
                if file.filename:
                    filename = save_file(file, 'image')
                    if filename:
                        images.append(filename)
        
        if 'videos' in request.files:
            for file in request.files.getlist('videos'):
                if file.filename:
                    filename = save_file(file, 'video')
                    if filename:
                        videos.append(filename)
        
        try:
            new_post = Post(
                content=content,
                user_id=current_user.id,
                images=','.join(images) if images else '',
                videos=','.join(videos) if videos else '',
                post_type='text' if not images and not videos else 'media'
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
                    <i class="fas fa-image"></i> Изображения (PNG, JPG, GIF)
                </label>
                <input type="file" name="images" class="form-input" multiple accept="image/*">
                <small style="color: #666; display: block; margin-top: 8px;">
                    <i class="fas fa-info-circle"></i> Можно выбрать несколько файлов
                </small>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-video"></i> Видео (MP4, MOV, AVI, MKV)
                </label>
                <input type="file" name="videos" class="form-input" multiple accept="video/*">
                <small style="color: #666; display: block; margin-top: 8px;">
                    <i class="fas fa-info-circle"></i> Максимальный размер файлов - 50 МБ
                </small>
            </div>
            
            <div class="info-box">
                <h4><i class="fas fa-lightbulb"></i> Советы по созданию постов</h4>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Делитесь интересными моментами из жизни</p>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Используйте эмодзи для выражения эмоций</p>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Добавляйте фото и видео для наглядности</p>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Будьте вежливы и уважайте других пользователей</p>
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
            flash('💔 Лайк удален', 'info')
        else:
            new_like = Like(user_id=current_user.id, post_id=post_id)
            db.session.add(new_like)
            flash('❤️ Посту понравилось!', 'success')
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect('/feed')

@app.route('/post/<int:post_id>')
@login_required
def view_post(post_id):
    try:
        post = Post.query.get(post_id)
        if not post:
            flash('Пост не найден', 'error')
            return redirect('/feed')
        
        author = User.query.get(post.user_id)
        if not author or author.is_banned:
            flash('Пользователь не найден или заблокирован', 'error')
            return redirect('/feed')
        
        add_view(post.id, current_user.id)
        
        post_content = get_emoji_html(post.content)
        
        media_html = ''
        if post.images:
            images = post.images.split(',')
            if any(images):
                media_html += '<div class="media-grid">'
                for img in images:
                    if img:
                        media_html += f'''
                        <div class="media-item">
                            <img src="/static/uploads/{img}" alt="Изображение" style="width: 100%; height: 180px; object-fit: cover;">
                        </div>
                        '''
                media_html += '</div>'
        
        comments_html = ''
        comments = Comment.query.filter_by(post_id=post_id, is_hidden=False).order_by(Comment.created_at.desc()).all()
        for comment in comments:
            comment_author = User.query.get(comment.user_id)
            if comment_author and not comment_author.is_banned:
                comments_html += f'''
                <div class="comment">
                    <div class="comment-header">
                        <strong>{comment_author.first_name} {comment_author.last_name}</strong>
                        <span>{comment.created_at.strftime('%d.%m.%Y %H:%M')}</span>
                    </div>
                    <p>{get_emoji_html(comment.content)}</p>
                </div>
                '''
        
        return render_page(f'Пост от {author.first_name}', f'''
        <div class="card">
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
                {f'<a href="/delete_post/{post.id}" class="btn btn-small btn-danger" onclick="return confirm(\'Вы уверены, что хотите удалить этот пост?\')">
                    <i class="fas fa-trash"></i> Удалить
                </a>' if current_user.id == post.user_id or current_user.is_admin else ''}
                <a href="/profile/{author.id}" class="btn btn-small">
                    <i class="fas fa-user"></i> Профиль автора
                </a>
            </div>
            
            <div class="comments-section">
                <h3><i class="fas fa-comments"></i> Комментарии</h3>
                
                <form method="POST" action="/add_comment/{post.id}" style="margin-bottom: 25px;">
                    <div class="form-group">
                        <textarea name="content" class="form-input" rows="3" placeholder="Добавить комментарий..." required></textarea>
                    </div>
                    <button type="submit" class="btn btn-small">
                        <i class="fas fa-paper-plane"></i> Отправить
                    </button>
                </form>
                
                {comments_html if comments_html else '''
                <div style="text-align: center; padding: 30px 20px; color: #999;">
                    <i class="fas fa-comment-slash" style="font-size: 3em; margin-bottom: 15px;"></i>
                    <p>Комментариев пока нет. Будьте первым!</p>
                </div>
                '''}
            </div>
        </div>
        ''')
        
    except Exception as e:
        flash(f'Ошибка загрузки поста: {str(e)}', 'error')
        return redirect('/feed')

@app.route('/add_comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    try:
        content = request.form.get('content', '').strip()
        
        if not content:
            flash('Комментарий не может быть пустым', 'error')
            return redirect(f'/post/{post_id}')
        
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
    
    return redirect(f'/post/{post_id}')

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    try:
        post = Post.query.get(post_id)
        
        if not post:
            flash('Пост не найден', 'error')
            return redirect('/feed')
        
        if current_user.id != post.user_id and not current_user.is_admin:
            flash('У вас нет прав для удаления этого поста', 'error')
            return redirect('/feed')
        
        db.session.delete(post)
        db.session.commit()
        
        flash('✅ Пост удален', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect('/feed')

# ========== ПРОФИЛИ ПОЛЬЗОВАТЕЛЕЙ ==========
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
                    <a href="/post/{post.id}" class="btn btn-small">Читать полностью</a>
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
        
        is_blocked = is_user_blocked(current_user.id, user_id)
        block_button = ''
        if current_user.id != user_id:
            if is_blocked:
                block_button = f'''
                <a href="/unblock/{user_id}" class="btn btn-warning">
                    <i class="fas fa-ban"></i> Разблокировать
                </a>
                '''
            else:
                block_button = f'''
                <a href="/block/{user_id}" class="btn btn-danger" onclick="return confirm('Вы уверены, что хотите заблокировать этого пользователя?')">
                    <i class="fas fa-ban"></i> Заблокировать
                </a>
                '''
        
        return render_page(f'Профиль {user.first_name}', f'''
        <div class="card">
            <div style="display: flex; align-items: center; margin-bottom: 30px;">
                <div class="avatar" style="width: 100px; height: 100px; font-size: 2em;">
                    {user.first_name[0]}{user.last_name[0] if user.last_name else ''}
                </div>
                <div style="margin-left: 30px;">
                    <h2 style="margin: 0;">{user.first_name} {user.last_name}</h2>
                    <p style="color: #666; margin: 10px 0;">
                        <i class="fas fa-at"></i> @{user.username}
                        {f'<span class="admin-badge"><i class="fas fa-crown"></i> Админ</span>' if user.is_admin else ''}
                        {f'<span class="banned-badge"><i class="fas fa-ban"></i> Забанен</span>' if user.is_banned else ''}
                    </p>
                    <p style="color: #666;">
                        <i class="fas fa-envelope"></i> {user.email} • 
                        <i class="fas fa-calendar"></i> Зарегистрирован {user.created_at.strftime('%d.%m.%Y')}
                    </p>
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
                {block_button}
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
            current_user.bio = request.form.get('bio', current_user.bio)
            
            birthday_str = request.form.get('birthday')
            if birthday_str:
                try:
                    current_user.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
                except:
                    current_user.birthday = None
            
            if 'avatar' in request.files:
                file = request.files['avatar']
                if file and file.filename:
                    filename = save_file(file, 'image')
                    if filename:
                        current_user.avatar_filename = filename
            
            db.session.commit()
            flash('✅ Профиль успешно обновлен!', 'success')
            return redirect(f'/profile/{current_user.id}')
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка обновления профиля: {str(e)}', 'error')
    
    return render_page('Редактировать профиль', f'''
    <div class="card">
        <h2><i class="fas fa-edit"></i> Редактировать профиль</h2>
        
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
            
            <div class="info-box">
                <h4><i class="fas fa-shield-alt"></i> Безопасность профиля</h4>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Ваш email и псевдоним нельзя изменить</p>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Для смены пароля обратитесь к администратору</p>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Вся информация защищена и конфиденциальна</p>
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
        if not user_to_follow or user_to_follow.is_banned:
            flash('Пользователь не найден или заблокирован', 'error')
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

@app.route('/block/<int:user_id>')
@login_required
def block_user(user_id):
    try:
        if current_user.id == user_id:
            flash('Нельзя заблокировать себя', 'error')
            return redirect(f'/profile/{user_id}')
        
        if is_user_blocked(current_user.id, user_id):
            flash('Пользователь уже заблокирован', 'info')
            return redirect(f'/profile/{user_id}')
        
        user_to_block = User.query.get(user_id)
        if not user_to_block:
            flash('Пользователь не найден', 'error')
            return redirect('/users')
        
        new_block = BlockedUser(blocker_id=current_user.id, blocked_id=user_id)
        db.session.add(new_block)
        db.session.commit()
        
        flash(f'✅ Пользователь {user_to_block.first_name} заблокирован', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(f'/profile/{user_id}')

@app.route('/unblock/<int:user_id>')
@login_required
def unblock_user(user_id):
    try:
        block = BlockedUser.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).first()
        
        if not block:
            flash('Пользователь не заблокирован', 'info')
            return redirect(f'/profile/{user_id}')
        
        user_to_unblock = User.query.get(user_id)
        
        db.session.delete(block)
        db.session.commit()
        
        flash(f'✅ Пользователь {user_to_unblock.first_name} разблокирован', 'success')
        
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
                (User.username.ilike(search_term)) |
                (User.email.ilike(search_term))
            )
        
        users = query.order_by(User.created_at.desc()).all()
        
        users_html = ''
        for user in users:
            if user.id == current_user.id:
                continue
                
            users_html += f'''
            <div class="user-card">
                <div style="display: flex; align-items: center; margin-bottom: 15px;">
                    <div class="avatar" style="width: 50px; height: 50px; font-size: 1em;">
                        {user.first_name[0]}{user.last_name[0] if user.last_name else ''}
                    </div>
                    <div style="margin-left: 15px;">
                        <strong style="color: #2a5298;">{user.first_name} {user.last_name}</strong>
                        <div style="font-size: 0.9em; color: #666;">
                            @{user.username}
                            {f'<span class="admin-badge">Админ</span>' if user.is_admin else ''}
                        </div>
                    </div>
                </div>
                
                <p style="font-size: 0.95em; color: #666; margin-bottom: 15px;">
                    <i class="fas fa-envelope"></i> {user.email}<br>
                    <i class="fas fa-calendar"></i> Зарегистрирован {user.created_at.strftime('%d.%m.%Y')}
                </p>
                
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
                    <input type="text" name="search" class="form-input" placeholder="Поиск по имени, фамилии, email..." value="{search}" style="min-width: 300px;">
                    <button type="submit" class="btn">
                        <i class="fas fa-search"></i> Найти
                    </button>
                </form>
            </div>
            
            {users_html if users_html else '''
            <div style="text-align: center; padding: 50px 20px;">
                <i class="fas fa-users" style="font-size: 4em; color: #e1e8ed; margin-bottom: 20px;"></i>
                <h3 style="color: #666; margin-bottom: 15px;">Пользователи не найдены</h3>
                <p style="color: #999; margin-bottom: 25px;">Попробуйте изменить параметры поиска</p>
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
            
            if is_user_blocked(current_user.id, other_user.id) or is_user_blocked(other_user.id, current_user.id):
                flash('Вы не можете общаться с этим пользователем из-за блокировки', 'error')
                return redirect('/messages')
            
            messages_list = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
                ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
            ).order_by(Message.created_at).all()
            
            for message in messages_list:
                if message.receiver_id == current_user.id and not message.is_read:
                    message.is_read = True
                    db.session.commit()
            
            chat_html = ''
            for message in messages_list:
                is_sent = message.sender_id == current_user.id
                chat_html += f'''
                <div class="chat-message {'message-sent' if is_sent else 'message-received'}">
                    <div class="message-bubble {'sent-bubble' if is_sent else 'received-bubble'}">
                        {get_emoji_html(message.content)}
                        <span class="message-time">
                            {message.created_at.strftime('%H:%M')} • 
                            {message.created_at.strftime('%d.%m.%Y')}
                            {'<i class="fas fa-check" style="margin-left: 5px;"></i>' if message.is_read and is_sent else ''}
                        </span>
                    </div>
                </div>
                '''
            
            return render_page(f'Чат с {other_user.first_name}', f'''
            <div class="card">
                <div style="display: flex; align-items: center; margin-bottom: 25px;">
                    <a href="/messages" class="btn btn-small" style="margin-right: 20px;">
                        <i class="fas fa-arrow-left"></i> Назад
                    </a>
                    <div class="avatar" style="width: 50px; height: 50px;">
                        {other_user.first_name[0]}{other_user.last_name[0] if other_user.last_name else ''}
                    </div>
                    <div style="margin-left: 15px;">
                        <h3 style="margin: 0;">{other_user.first_name} {other_user.last_name}</h3>
                        <p style="color: #666; margin: 5px 0 0 0;">
                            @{other_user.username}
                        </p>
                    </div>
                </div>
                
                <div style="height: 500px; overflow-y: auto; padding: 20px; background: rgba(248, 249, 250, 0.5); border-radius: 15px; margin-bottom: 25px;">
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
            conversations = []
            
            sent_messages = Message.query.filter_by(sender_id=current_user.id).all()
            received_messages = Message.query.filter_by(receiver_id=current_user.id).all()
            
            all_messages = sent_messages + received_messages
            
            user_dict = {}
            for message in all_messages:
                other_id = message.sender_id if message.sender_id != current_user.id else message.receiver_id
                if other_id not in user_dict:
                    other_user = User.query.get(other_id)
                    if other_user and not other_user.is_banned:
                        last_message = Message.query.filter(
                            ((Message.sender_id == current_user.id) & (Message.receiver_id == other_id)) |
                            ((Message.sender_id == other_id) & (Message.receiver_id == current_user.id))
                        ).order_by(Message.created_at.desc()).first()
                        
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
            for other_id, data in sorted(user_dict.items(), 
                                      key=lambda x: x[1]['last_message'].created_at if x[1]['last_message'] else datetime.min, 
                                      reverse=True):
                other_user = data['user']
                last_message = data['last_message']
                unread_count = data['unread_count']
                
                last_message_text = last_message.content if last_message else 'Нет сообщений'
                if len(last_message_text) > 50:
                    last_message_text = last_message_text[:50] + '...'
                
                conversations_html += f'''
                <a href="/messages/{other_user.id}" style="text-decoration: none; color: inherit;">
                    <div class="user-card" style="cursor: pointer; transition: all 0.3s ease;">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center;">
                                <div class="avatar" style="width: 50px; height: 50px;">
                                    {other_user.first_name[0]}{other_user.last_name[0] if other_user.last_name else ''}
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
            
            return render_page('Сообщения', f'''
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
                    <h2 style="margin: 0;"><i class="fas fa-envelope"></i> Сообщения</h2>
                    <span style="color: #666;">
                        <i class="fas fa-bell"></i> Непрочитанных: {get_unread_messages_count(current_user.id)}
                    </span>
                </div>
                
                {conversations_html if conversations_html else '''
                <div style="text-align: center; padding: 50px 20px;">
                    <i class="fas fa-envelope-open" style="font-size: 4em; color: #e1e8ed; margin-bottom: 20px;"></i>
                    <h3 style="color: #666; margin-bottom: 15px;">Сообщений нет</h3>
                    <p style="color: #999; margin-bottom: 25px;">Начните общение с другими пользователями</p>
                    <a href="/users" class="btn">
                        <i class="fas fa-users"></i> Найти пользователей
                    </a>
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
        if not receiver or receiver.is_banned:
            flash('Пользователь не найден или заблокирован', 'error')
            return redirect('/messages')
        
        if is_user_blocked(current_user.id, receiver.id) or is_user_blocked(receiver.id, current_user.id):
            flash('Вы не можете отправлять сообщения этому пользователю', 'error')
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

# ========== РЕКЛАМА ==========
@app.route('/create_ad', methods=['GET', 'POST'])
@login_required
def create_ad():
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            
            if not title or not description:
                flash('Заполните все обязательные поля', 'error')
                return redirect('/create_ad')
            
            image_filename = None
            video_filename = None
            
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    image_filename = save_file(file, 'image')
            
            if 'video' in request.files:
                file = request.files['video']
                if file and file.filename:
                    video_filename = save_file(file, 'video')
            
            new_ad = Advertisement(
                user_id=current_user.id,
                title=title,
                description=description,
                image_filename=image_filename,
                video_filename=video_filename,
                status='pending'
            )
            
            db.session.add(new_ad)
            db.session.commit()
            
            flash('✅ Реклама успешно создана и отправлена на модерацию!', 'success')
            return redirect('/create_ad')
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка при создании рекламы: {str(e)}', 'error')
    
    return render_page('Создать рекламу', '''
    <div class="card">
        <h2><i class="fas fa-bullhorn"></i> Создать рекламное объявление</h2>
        
        <form method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-heading"></i> Заголовок
                </label>
                <input type="text" name="title" class="form-input" placeholder="Название вашего объявления" required>
            </div>
            
            <div class="form-group">
                <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                    <i class="fas fa-align-left"></i> Описание
                </label>
                <textarea name="description" class="form-input" rows="6" placeholder="Подробное описание вашего предложения..." required></textarea>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                <div class="form-group">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-image"></i> Изображение
                    </label>
                    <input type="file" name="image" class="form-input" accept="image/*">
                </div>
                
                <div class="form-group">
                    <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                        <i class="fas fa-video"></i> Видео
                    </label>
                    <input type="file" name="video" class="form-input" accept="video/*">
                </div>
            </div>
            
            <div class="info-box">
                <h4><i class="fas fa-info-circle"></i> Правила размещения рекламы</h4>
                <p><i class="fas fa-exclamation-triangle" style="color: #ffc107;"></i> Реклама проходит модерацию администрацией</p>
                <p><i class="fas fa-exclamation-triangle" style="color: #ffc107;"></i> Запрещена реклама запрещенных товаров и услуг</p>
                <p><i class="fas fa-exclamation-triangle" style="color: #ffc107;"></i> Обман и мошенничество недопустимы</p>
                <p><i class="fas fa-check" style="color: #28a745;"></i> Вся реклама проверяется в течение 24 часов</p>
            </div>
            
            <button type="submit" class="btn" style="width: 100%; padding: 18px; font-size: 18px;">
                <i class="fas fa-paper-plane"></i> Отправить на модерацию
            </button>
        </form>
    </div>
    ''')

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
        
        recent_posts_html = ''
        for post in recent_posts:
            author = User.query.get(post.user_id)
            recent_posts_html += f'''
            <tr>
                <td>{post.id}</td>
                <td>{author.first_name if author else 'Unknown'} {author.last_name if author else ''}</td>
                <td>{post.content[:50]}...</td>
                <td>{post.created_at.strftime('%d.%m.%Y %H:%M')}</td>
                <td>{post.views_count}</td>
                <td>
                    <a href="/admin/delete_post/{post.id}" class="btn btn-small btn-danger" onclick="return confirm('Удалить этот пост?')">
                        <i class="fas fa-trash"></i>
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
                    <div class="stat-number">{total_messages}</div>
                    <div class="stat-label">Сообщений</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">{pending_ads}</div>
                    <div class="stat-label">Реклама на модерации</div>
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
            <h3><i class="fas fa-newspaper"></i> Последние посты</h3>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Автор</th>
                        <th>Содержание</th>
                        <th>Дата</th>
                        <th>Просмотры</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody>
                    {recent_posts_html}
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h3><i class="fas fa-tools"></i> Инструменты администратора</h3>
            <div style="display: flex; gap: 15px; flex-wrap: wrap; margin-top: 20px;">
                <a href="/admin/backup" class="btn">
                    <i class="fas fa-database"></i> Создать бэкап
                </a>
                <a href="/admin/restore" class="btn">
                    <i class="fas fa-history"></i> Восстановить
                </a>
                <a href="/admin/ads" class="btn">
                    <i class="fas fa-bullhorn"></i> Модерация рекламы
                </a>
                <a href="/admin/settings" class="btn">
                    <i class="fas fa-cog"></i> Настройки
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

@app.route('/admin/delete_post/<int:post_id>')
@login_required
def admin_delete_post(post_id):
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    try:
        post = Post.query.get(post_id)
        if post:
            db.session.delete(post)
            db.session.commit()
            flash('✅ Пост удален администратором', 'success')
        else:
            flash('Пост не найден', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect('/admin')

@app.route('/admin/user/<int:user_id>')
@login_required
def admin_edit_user(user_id):
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    try:
        user = User.query.get(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect('/admin')
        
        return render_page(f'Редактирование пользователя {user.username}', f'''
        <div class="card">
            <h2><i class="fas fa-user-edit"></i> Редактирование пользователя</h2>
            
            <form method="POST" action="/admin/update_user/{user_id}">
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
                
                <div class="info-box">
                    <h4><i class="fas fa-exclamation-triangle"></i> Важно!</h4>
                    <p>Изменение статуса администратора или блокировка пользователя вступают в силу немедленно.</p>
                    <p>Будьте осторожны при изменении данных пользователей.</p>
                </div>
                
                <div style="display: flex; gap: 15px; margin-top: 25px;">
                    <button type="submit" class="btn">
                        <i class="fas fa-save"></i> Сохранить изменения
                    </button>
                    <a href="/admin" class="btn btn-danger">
                        <i class="fas fa-times"></i> Отмена
                    </a>
                </div>
            </form>
        </div>
        ''')
        
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect('/admin')

@app.route('/admin/update_user/<int:user_id>', methods=['POST'])
@login_required
def admin_update_user(user_id):
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    try:
        user = User.query.get(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect('/admin')
        
        user.first_name = request.form.get('first_name', user.first_name)
        user.last_name = request.form.get('last_name', user.last_name)
        user.email = request.form.get('email', user.email)
        user.username = request.form.get('username', user.username)
        user.is_admin = request.form.get('is_admin') == '1'
        user.is_banned = request.form.get('is_banned') == '1'
        
        db.session.commit()
        flash('✅ Данные пользователя обновлены', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка обновления: {str(e)}', 'error')
    
    return redirect('/admin')

# ========== СТАТИЧЕСКИЕ ФАЙЛЫ ==========
@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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
