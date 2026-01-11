"""
MateuGram - Синяя социальная сеть
Версия с администратором, блокировкой пользователей, комментариями и лайками
"""

from flask import Flask, render_template_string, request, redirect, url_for, flash, get_flashed_messages
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

# Простой тестовый маршрут
@app.route('/test')
def test():
    return '✅ MateuGram работает! Resend: ' + ('Настроен' if os.environ.get('RESEND_API_KEY') else 'Не настроен')

@app.route('/health')
def health():
    return 'OK', 200

# Настройки приложения
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mateugram-secret-key-2024-change-this')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mateugram_admin.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Настройки для загрузки файлов
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB максимум
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

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
    is_admin = db.Column(db.Boolean, default=False)  # Администратор
    is_banned = db.Column(db.Boolean, default=False)  # Забанен администратором
    bio = db.Column(db.Text, default='')
    avatar_filename = db.Column(db.String(200), default='default_avatar.png')
    
    posts = db.relationship('Post', backref='author', lazy=True, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy=True, cascade='all, delete-orphan')
    
    # Связь для блокировок (кто кого заблокировал)
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
    
    # Новые отношения для комментариев и лайков
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
    
    # Уникальное ограничение: один пользователь может лайкнуть пост только один раз
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
    blocker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Кто заблокировал
    blocked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Кого заблокировали
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Уникальное ограничение, чтобы нельзя было заблокировать одного пользователя дважды
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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_avatar(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{secrets.token_hex(8)}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        return unique_filename
    return None

def send_verification_email(user_email, verification_code, user_name):
    """Упрощенная отправка email - выводит код в консоль"""
    print(f"\n" + "="*60)
    print(f"📧 КОД ПОДТВЕРЖДЕНИЯ ДЛЯ РЕГИСТРАЦИИ")
    print(f"👤 Имя: {user_name}")
    print(f"📧 Email: {user_email}")
    print(f"🔢 КОД: {verification_code}")
    print("="*60 + "\n")
    
    # Всегда возвращаем True для тестирования
    return True

def resend_verification_code(user_id):
    """Генерирует и отправляет новый код подтверждения"""
    user = User.query.get(user_id)
    if not user:
        return False, "Пользователь не найден"
    
    new_code = str(secrets.randbelow(900000) + 100000)
    user.verification_code = new_code
    db.session.commit()
    
    success = send_verification_email(
        user.email, 
        new_code, 
        f"{user.first_name} {user.last_name}"
    )
    
    if success:
        return True, f"✅ Новый код отправлен на {user.email}"
    else:
        return False, "❌ Ошибка отправки email"

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

def is_user_blocked(blocker_id, blocked_id):
    """Проверяет, заблокировал ли пользователь другого пользователя"""
    return BlockedUser.query.filter_by(blocker_id=blocker_id, blocked_id=blocked_id).first() is not None

def block_user(blocker_id, blocked_id):
    """Блокирует пользователя"""
    if blocker_id == blocked_id:
        return False, "Нельзя заблокировать самого себя"
    
    if is_user_blocked(blocker_id, blocked_id):
        return False, "Пользователь уже заблокирован"
    
    blocked_user = BlockedUser(blocker_id=blocker_id, blocked_id=blocked_id)
    db.session.add(blocked_user)
    db.session.commit()
    
    blocked = User.query.get(blocked_id)
    return True, f"✅ Пользователь {blocked.first_name} {blocked.last_name} заблокирован"

def unblock_user(blocker_id, blocked_id):
    """Разблокирует пользователя"""
    blocked_record = BlockedUser.query.filter_by(blocker_id=blocker_id, blocked_id=blocked_id).first()
    
    if not blocked_record:
        return False, "Пользователь не был заблокирован"
    
    db.session.delete(blocked_record)
    db.session.commit()
    
    blocked = User.query.get(blocked_id)
    return True, f"✅ Пользователь {blocked.first_name} {blocked.last_name} разблокирован"

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

def is_post_liked_by_user(post_id, user_id):
    """Проверяет, лайкнул ли пользователь пост"""
    return Like.query.filter_by(post_id=post_id, user_id=user_id).first() is not None

def get_like_count(post_id):
    """Получает количество лайков поста"""
    return Like.query.filter_by(post_id=post_id).count()

def get_comment_count(post_id):
    """Получает количество комментариев поста"""
    return Comment.query.filter_by(post_id=post_id).count()

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
        .avatar-small {{
            width: 40px;
            height: 40px;
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
        .banned-label {{
            background: #dc3545;
            color: white;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 12px;
            margin-left: 10px;
        }}
        .admin-label {{
            background: #6f42c1;
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
        .like-active {{
            color: #e83e8c;
            font-weight: bold;
        }}
        .comment-form {{
            margin-top: 15px;
        }}
        .comment-input {{
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 8px;
            resize: vertical;
            min-height: 60px;
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
    // Таймер для повторной отправки
    function startResendTimer(seconds) {{
        const btn = document.getElementById('resendBtn');
        const timerText = document.getElementById('resendTimer');
        
        if (!btn || !timerText) return;
        
        btn.disabled = true;
        let timeLeft = seconds;
        
        const timer = setInterval(function() {{
            timerText.textContent = 'Повторно отправить можно через ' + timeLeft + ' секунд';
            timeLeft--;
            
            if (timeLeft < 0) {{
                clearInterval(timer);
                btn.disabled = false;
                timerText.textContent = 'Можно отправить код повторно';
            }}
        }}, 1000);
    }}
    
    // Подтверждение удаления
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
    
    // Подтверждение жалобы
    function confirmReport(itemType, itemId) {{
        if (confirm('Вы уверены, что хотите пожаловаться на этот контент?\\n\\nКонтент будет скрыт после 3 жалоб.')) {{
            window.location.href = '/report/' + itemType + '/' + itemId;
        }}
    }}
    
    // Подтверждение блокировки
    function confirmBlock(userId, userName) {{
        if (confirm('Вы уверены, что хотите заблокировать пользователя ' + userName + '?\\n\\nВы больше не сможете видеть его посты и сообщения.')) {{
            window.location.href = '/block_user/' + userId;
        }}
    }}
    
    // Подтверждение разблокировки
    function confirmUnblock(userId, userName) {{
        if (confirm('Вы уверены, что хотите разблокировать пользователя ' + userName + '?')) {{
            window.location.href = '/unblock_user/' + userId;
        }}
    }}
    
    // Подтверждение бана (админ)
    function confirmBan(userId, userName) {{
        if (confirm('Вы уверены, что хотите ЗАБАНИТЬ пользователя ' + userName + '?\\n\\nОн больше не сможет заходить в систему!')) {{
            window.location.href = '/admin/ban_user/' + userId;
        }}
    }}
    
    // Подтверждение разбана (админ)
    function confirmUnban(userId, userName) {{
        if (confirm('Вы уверены, что хотите РАЗБАНИТЬ пользователя ' + userName + '?')) {{
            window.location.href = '/admin/unban_user/' + userId;
        }}
    }}
    
    // Подтверждение удаления аккаунта (админ)
    function confirmDeleteAccount(userId, userName) {{
        if (confirm('⚠️ ВНИМАНИЕ! Вы уверены, что хотите УДАЛИТЬ аккаунт пользователя ' + userName + '?\\n\\nЭто действие необратимо! Все посты и сообщения пользователя будут удалены!')) {{
            window.location.href = '/admin/delete_user/' + userId;
        }}
    }}
    
    // Назначение админа
    function confirmMakeAdmin(userId, userName) {{
        if (confirm('Вы уверены, что хотите назначить ' + userName + ' администратором?\\n\\nОн получит полный доступ к панели администратора.')) {{
            window.location.href = '/admin/make_admin/' + userId;
        }}
    }}
    
    // Снятие прав админа
    function confirmRemoveAdmin(userId, userName) {{
        if (confirm('Вы уверены, что хотите снять права администратора у ' + userName + '?')) {{
            window.location.href = '/admin/remove_admin/' + userId;
        }}
    }}
    
    // Запускаем таймер при загрузке страницы
    document.addEventListener('DOMContentLoaded', function() {{
        const resendBtn = document.getElementById('resendBtn');
        if (resendBtn && resendBtn.disabled) {{
            startResendTimer(60);
        }}
    }});
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
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Блокировка пользователей</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Админ-панель (для MateuGram)</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Система жалоб на контент</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Личные сообщения</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Комментарии и лайки</li>
            <li style="padding: 10px 0;">✅ Назначение администраторов</li>
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

# ========== НОВЫЕ ФУНКЦИИ: КОММЕНТАРИИ И ЛАЙКИ ==========

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

# ========== АДМИН-ПАНЕЛЬ С НАЗНАЧЕНИЕМ АДМИНОВ ==========

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
        <a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Пользователи</a>
        <a href="/admin/admins" class="nav-btn active" style="background: #6f42c1; border-color: #6f42c1;">👑 Администраторы</a>
        <a href="/admin/reports" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">📊 Жалобы</a>
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 20px;">👑 Управление администраторами</h2>
        
        <div class="admin-actions">
            <h3 style="color: #6f42c1; margin-bottom: 15px;">Добавить администратора</h3>
            <p>Чтобы добавить администратора, сначала найдите пользователя на странице 
            <a href="/admin/users" style="color: #6f42c1;">"Управление пользователями"</a>, 
            затем нажмите кнопку "Назначить администратором".</p>
        </div>
        
        <h3 style="color: #2a5298; margin: 25px 0 15px 0;">Текущие администраторы ({len(admins)})</h3>
        
        <div class="user-list">
            {admins_html if admins_html else '<p style="text-align: center; color: #666; padding: 40px;">Нет администраторов.</p>'}
        </div>
    </div>'''
    
    return render_page('Админ-панель - Администраторы', content)

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        default_avatar_path = os.path.join('static', 'uploads', 'default_avatar.png')
        if not os.path.exists(default_avatar_path):
            default_avatar_svg = '''<svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
                <rect width="200" height="200" fill="#2a5298"/>
                <text x="100" y="110" font-family="Arial" font-size="80" fill="white" text-anchor="middle" alignment-baseline="middle">👤</text>
            </svg>'''
            with open(default_avatar_path, 'w') as f:
                f.write(default_avatar_svg)
        
        print("✅ База данных создана")
    
    print("\n" + "="*60)
    print("🔵 MateuGram с админ-панелью и блокировками запущен!")
    print("🌐 Откройте: http://127.0.0.1:5000")
    print("="*60)
    print("\n👑 АДМИНИСТРАТОР:")
    print("   Для получения прав администратора зарегистрируйтесь с псевдонимом 'MateuGram'")
    print("\n📋 ОСНОВНЫЕ ФУНКЦИИ:")
    print("   1. 👑 Админ-панель для пользователя MateuGram")
    print("   2. 🚫 Блокировка пользователей")
    print("   3. 👮 Баны и удаление аккаунтов")
    print("   4. 📊 Система жалоб и модерации")
    print("   5. 💬 Личные сообщения")
    print("   6. ❤️ Лайки и комментарии")
    print("   7. 👑 Назначение администраторов")
    print("="*60)
    
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=False)

