"""
MateuGram - Синяя социальная сеть
Версия с администратором и блокировкой пользователей
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
app.config['SECRET_KEY'] = 'mateugram-secret-key-2024-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mateugram_admin.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Настройки для загрузки файлов
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB максимум
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Создаем папку для загрузок, если она не существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ========== НАСТРОЙКИ EMAIL ==========
# Используем mail.ru
app.config['MAIL_SERVER'] = 'smtp.mail.ru'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'mcrmateucraft@mail.ru'  # Замените на вашу почту
app.config['MAIL_PASSWORD'] = 'f6wkngtymAFi2BVxa4Iy'  # Замените на ваш пароль
app.config['MAIL_DEFAULT_SENDER'] = 'MateuGram <mcrmateucraft@mail.ru>'

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
    """Отправляет код подтверждения на email"""
    print(f"\n📧 ОТПРАВЛЯЮ ПИСЬМО НА: {user_email}")
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Код подтверждения MateuGram'
        msg['From'] = app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = user_email
        
        text = f"""Здравствуйте, {user_name}!

Ваш код подтверждения для MateuGram: {verification_code}

Введите этот код на сайте для завершения регистрации.

С уважением,
Команда MateuGram"""
        
        html = f"""<html>
<body style="font-family: Arial, sans-serif; background: #f8f9fa; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px;">
        <h2 style="color: #2a5298; text-align: center;">🔵 MateuGram</h2>
        <h3>Здравствуйте, {user_name}!</h3>
        <p>Для завершения регистрации введите код подтверждения:</p>
        <div style="
            font-size: 32px;
            font-weight: bold;
            color: #2a5298;
            padding: 20px;
            background: #f0f0f0;
            border-radius: 10px;
            margin: 20px 0;
            text-align: center;
            letter-spacing: 5px;
        ">{verification_code}</div>
        <p><strong>Код действителен 10 минут</strong></p>
        <p>Если вы не регистрировались в MateuGram, проигнорируйте это письмо.</p>
    </div>
</body>
</html>"""
        
        part1 = MIMEText(text, 'plain', 'utf-8')
        part2 = MIMEText(html, 'html', 'utf-8')
        msg.attach(part1)
        msg.attach(part2)
        
        with smtplib.SMTP_SSL(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
            server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            server.send_message(msg)
        
        print(f"✅ Письмо отправлено на {user_email}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        print(f"🔢 КОД ДЛЯ {user_email}: {verification_code}")
        return False

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
            <li style="padding: 10px 0;">✅ Аватарки и описание профиля</li>
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
        
        verification_code = str(secrets.randbelow(900000) + 100000)
        
        # Если пользователь регистрируется как MateuGram, делаем его администратором
        is_admin = (username.lower() == 'mateugram')
        
        new_user = User(
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            password_hash=generate_password_hash(password),
            verification_code=verification_code,
            is_active=True,
            is_admin=is_admin
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        send_verification_email(email, verification_code, f"{first_name} {last_name}")
        
        if is_admin:
            flash(f'✅ Регистрация успешна! Вы зарегистрированы как администратор. Код отправлен на {email}', 'success')
        else:
            flash(f'✅ Регистрация успешна! Код отправлен на {email}', 'success')
        
        return redirect(f'/verify_email/{new_user.id}')
    
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
            
            if not user.email_verified:
                flash('Подтвердите email для входа', 'error')
                return redirect(f'/verify_email/{user.id}')
            
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

@app.route('/verify_email/<int:user_id>', methods=['GET', 'POST'])
def verify_email(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        code = request.form['code']
        
        if code == user.verification_code:
            user.email_verified = True
            user.verification_code = None
            db.session.commit()
            
            login_user(user, remember=True)
            
            if user.is_admin:
                flash('👑 Email подтвержден! Вы вошли как администратор.', 'success')
            else:
                flash('✅ Email подтвержден! Добро пожаловать!', 'success')
            
            return redirect('/feed')
        else:
            flash('❌ Неверный код подтверждения', 'error')
    
    content = f'''<div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">📧 Подтверждение Email</h2>
        
        <div style="background: #e7f3ff; border-radius: 8px; padding: 15px; margin: 20px 0;">
            <p>Код подтверждения отправлен на email:</p>
            <p style="font-weight: bold; font-size: 1.1em; margin: 10px 0;">{user.email}</p>
            <p style="color: #666; font-size: 0.9em;">
                Проверьте папку "Входящие" или "Спам".
            </p>
        </div>
        
        <form method="POST" action="/verify_email/{user_id}">
            <div class="form-group">
                <label class="form-label">🔢 Код подтверждения (6 цифр)</label>
                <input type="text" name="code" class="form-input" placeholder="Введите 6 цифр" required maxlength="6" pattern="[0-9]{{6}}">
            </div>
            
            <button type="submit" class="btn">✅ Подтвердить</button>
        </form>
        
        <div class="resend-info">
            <p>Не получили код?</p>
            <form method="POST" action="/resend_code/{user_id}" style="margin-top: 15px;">
                <button type="submit" class="btn btn-warning" id="resendBtn" style="width: auto;">
                    🔄 Отправить код ещё раз
                </button>
                <p class="resend-timer" id="resendTimer">Можно отправить код повторно</p>
            </form>
        </div>
    </div>'''
    
    return render_page('Подтверждение Email', content)

@app.route('/resend_code/<int:user_id>', methods=['POST'])
def resend_code(user_id):
    success, message = resend_verification_code(user_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(f'/verify_email/{user_id}')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('👋 Вы вышли из системы', 'success')
    return redirect('/')

@app.route('/feed')
@login_required
def feed():
    if current_user.is_banned:
        flash('❌ Ваш аккаунт заблокирован администратором', 'error')
        logout_user()
        return redirect('/login')
    
    unread_count = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
    
    # Получаем ID заблокированных пользователей
    blocked_ids = [b.blocked_id for b in BlockedUser.query.filter_by(blocker_id=current_user.id).all()]
    
    # Показываем только посты незаблокированных пользователей
    posts = Post.query.filter(~Post.user_id.in_(blocked_ids)).order_by(Post.created_at.desc()).all()
    
    posts_html = ""
    if posts:
        for post in posts:
            can_delete = post.user_id == current_user.id
            is_blocked = post.user_id in blocked_ids
            
            posts_html += f'''<div class="post{' hidden' if post.is_hidden else ''}">
                <div class="post-header">
                    <img src="/static/uploads/{post.author.avatar_filename}" class="avatar avatar-small" alt="{post.author.username}">
                    <div>
                        <div class="post-author">{post.author.first_name} {post.author.last_name}</div>
                        <small>@{post.author.username}</small>
                        {f'<span class="admin-label">👑 Админ</span>' if post.author.is_admin else ''}
                        {f'<span class="banned-label">🚫 Забанен</span>' if post.author.is_banned else ''}
                    </div>
                    <div class="post-time">{post.created_at.strftime('%d.%m.%Y %H:%M')}</div>
                    {f'<span class="warning-badge">⚠️ {post.reports_count} жалоб</span>' if post.reports_count > 0 else ''}
                    {f'<span class="hidden-label">🚫 Скрыто</span>' if post.is_hidden else ''}
                </div>
                <div class="post-content">{post.content}</div>
                <div style="color: #666; font-size: 0.9em;">
                    📝 {post.post_type.capitalize()}
                </div>
                <div class="post-actions">
                    <a href="/profile/{post.author.id}" class="btn btn-small btn-secondary">👤 Профиль</a>
                    {f'<a href="/send_message/{post.author.id}" class="btn btn-small">💬 Написать</a>' if not is_blocked else ''}
                    {f'<button onclick="confirmDelete(\'пост\', {post.id})" class="btn btn-small btn-danger">🗑 Удалить</button>' if can_delete else ''}
                    {f'<button onclick="confirmReport(\'post\', {post.id})" class="btn btn-small btn-report">🚩 Пожаловаться</button>' if post.user_id != current_user.id and not post.is_hidden else ''}
                    {f'<button onclick="confirmBlock({post.author.id}, \'{post.author.username}\')" class="btn btn-small btn-block">🚫 Заблокировать</button>' if not is_blocked and post.user_id != current_user.id else ''}
                    {f'<button onclick="confirmUnblock({post.author.id}, \'{post.author.username}\')" class="btn btn-small btn-warning">✅ Разблокировать</button>' if is_blocked else ''}
                </div>
            </div>'''
    else:
        posts_html = '<p style="text-align: center; color: #666; padding: 40px;">Пока нет постов. Будьте первым!</p>'
    
    # Админ-панель
    admin_panel = ""
    if current_user.is_admin:
        admin_panel = f'''<div class="admin-actions">
            <h3 style="color: #6f42c1; margin-bottom: 15px;">👑 Панель администратора</h3>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <a href="/admin/users" class="btn btn-admin btn-small">👥 Управление пользователями</a>
                <a href="/admin/reports" class="btn btn-admin btn-small">📊 Жалобы и модерация</a>
            </div>
        </div>'''
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn active">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения {f"<span class='unread-badge'>{unread_count}</span>" if unread_count > 0 else ""}</a>
        <a href="/users" class="nav-btn">👥 Пользователи</a>
        <a href="/profile/{current_user.id}" class="nav-btn">👤 Мой профиль</a>
        <a href="/create_post" class="nav-btn">📝 Создать пост</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    {admin_panel}
    
    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">📰 Лента новостей</h2>
        
        {posts_html}
    </div>'''
    
    return render_page('Лента', content)

@app.route('/blocked_users')
@login_required
def blocked_users():
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
        <a href="/users" class="nav-btn">👥 Пользователи</a>
        <a href="/profile/{current_user.id}" class="nav-btn">👤 Мой профиль</a>
        <a href="/blocked_users" class="nav-btn active">🚫 Заблокированные</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">🚫 Заблокированные пользователи</h2>
        
        <p style="margin-bottom: 20px; color: #666;">
            Здесь отображаются пользователи, которых вы заблокировали. Вы не будете видеть их посты и сообщения.
        </p>
        
        <div class="blocked-users-list">
            {blocked_html}
        </div>
        
        <div style="margin-top: 20px;">
            <a href="/users" class="btn">👥 Посмотреть всех пользователей</a>
        </div>
    </div>'''
    
    return render_page('Заблокированные пользователи', content)

@app.route('/block_user/<int:user_id>')
@login_required
def block_user_route(user_id):
    user_to_block = User.query.get_or_404(user_id)
    
    if user_to_block.id == current_user.id:
        flash('❌ Нельзя заблокировать самого себя', 'error')
        return redirect('/feed')
    
    success, message = block_user(current_user.id, user_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect('/feed')

@app.route('/unblock_user/<int:user_id>')
@login_required
def unblock_user_route(user_id):
    success, message = unblock_user(current_user.id, user_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect('/blocked_users')

@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)
    
    # Проверяем, не заблокирован ли этот пользователь
    is_blocked = is_user_blocked(current_user.id, user_id)
    
    if is_blocked:
        flash('🚫 Этот пользователь заблокирован вами. Вы не можете просматривать его профиль.', 'error')
        return redirect('/feed')
    
    user_posts = Post.query.filter_by(user_id=user_id).order_by(Post.created_at.desc()).limit(10).all()
    
    posts_html = ""
    if user_posts:
        for post in user_posts:
            posts_html += f'''<div class="post{' hidden' if post.is_hidden else ''}">
                <div class="post-header">
                    <div class="post-author">{user.first_name} {user.last_name}</div>
                    <div class="post-time">{post.created_at.strftime('%d.%m.%Y %H:%M')}</div>
                    {f'<span class="warning-badge">⚠️ {post.reports_count} жалоб</span>' if post.reports_count > 0 else ''}
                </div>
                <div class="post-content">{post.content}</div>
            </div>'''
    else:
        posts_html = '<p style="text-align: center; color: #666; padding: 20px;">Пользователь пока не опубликовал постов.</p>'
    
    is_own_profile = user.id == current_user.id
    
    content = f'''<div class="profile-header">
        <img src="/static/uploads/{user.avatar_filename}" class="profile-avatar" alt="{user.username}">
        <div class="profile-info">
            <h2>{user.first_name} {user.last_name}</h2>
            <p style="color: #666; font-size: 1.1em;">@{user.username}</p>
            {f'<span class="admin-label">👑 Администратор</span>' if user.is_admin else ''}
            {f'<span class="banned-label">🚫 Забанен</span>' if user.is_banned else ''}
            <p>Зарегистрирован: {user.created_at.strftime('%d.%m.%Y')}</p>
            
            <div style="margin-top: 20px;">
                <a href="/send_message/{user.id}" class="btn">💬 Написать сообщение</a>
                {f'<a href="/edit_profile" class="btn btn-secondary" style="margin-left: 10px;">✏️ Редактировать профиль</a>' if is_own_profile else ''}
                {f'<button onclick="confirmBlock({user.id}, \'{user.username}\')" class="btn btn-block" style="margin-left: 10px;">🚫 Заблокировать</button>' if not is_own_profile and not is_blocked else ''}
                {f'<button onclick="confirmUnblock({user.id}, \'{user.username}\')" class="btn btn-warning" style="margin-left: 10px;">✅ Разблокировать</button>' if not is_own_profile and is_blocked else ''}
            </div>
        </div>
    </div>
    
    <div class="card">
        <h3 style="color: #2a5298; margin-bottom: 15px;">📝 О себе</h3>
        {f'<div class="bio-text">{user.bio if user.bio else "Пользователь пока ничего не рассказал о себе."}</div>'}
    </div>
    
    <div class="card">
        <h3 style="color: #2a5298; margin-bottom: 15px;">📰 Последние посты</h3>
        {posts_html}
    </div>'''
    
    return render_page(f'Профиль {user.first_name}', content)

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        user = current_user
        user.bio = request.form['bio']
        
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '':
                filename = save_avatar(file)
                if filename:
                    if user.avatar_filename != 'default_avatar.png':
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], user.avatar_filename)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    user.avatar_filename = filename
        
        db.session.commit()
        flash('✅ Профиль успешно обновлен!', 'success')
        return redirect(f'/profile/{user.id}')
    
    content = f'''<div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">✏️ Редактирование профиля</h2>
        
        <form method="POST" action="/edit_profile" enctype="multipart/form-data">
            <div class="form-group">
                <label class="form-label">🖼 Аватарка</label>
                <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 15px;">
                    <img src="/static/uploads/{current_user.avatar_filename}" class="avatar" style="width: 100px; height: 100px;">
                    <div>
                        <input type="file" name="avatar" accept="image/*">
                        <small style="color: #666; display: block; margin-top: 5px;">
                            Поддерживаются: PNG, JPG, JPEG, GIF (макс. 2MB)
                        </small>
                    </div>
                </div>
            </div>
            
            <div class="form-group">
                <label class="form-label">📝 О себе</label>
                <textarea name="bio" class="form-input" rows="5" placeholder="Расскажите о себе...">{current_user.bio if current_user.bio else ''}</textarea>
            </div>
            
            <div style="display: flex; gap: 15px; margin-top: 30px;">
                <button type="submit" class="btn">💾 Сохранить</button>
                <a href="/profile/{current_user.id}" class="btn btn-secondary">← Назад к профилю</a>
            </div>
        </form>
    </div>'''
    
    return render_page('Редактирование профиля', content)

@app.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        content = request.form['content']
        post_type = request.form['post_type']
        
        is_clean, found_words = check_content_for_report(content)
        
        if not is_clean:
            flash(f'⚠️ В вашем посте обнаружены слова, на которые могут пожаловаться: {", ".join(found_words)}. Вы все равно можете опубликовать пост, но будьте осторожны.', 'warning')
        
        new_post = Post(
            content=content,
            post_type=post_type,
            user_id=current_user.id
        )
        
        db.session.add(new_post)
        db.session.commit()
        
        flash('✅ Пост опубликован!', 'success')
        return redirect('/feed')
    
    content = '''<div class="card">
        <h2 style="color: #2a5298; margin-bottom: 25px;">📝 Создать новый пост</h2>
        
        <div class="content-warning">
            <strong>⚠️ Внимание:</strong> Посты с запрещенными словами (мат, политика, религия) могут получить жалобы от других пользователей. После 3 жалоб пост будет автоматически скрыт.
        </div>
        
        <form method="POST" action="/create_post">
            <div class="form-group">
                <label class="form-label">💬 Текст поста</label>
                <textarea name="content" class="form-input" rows="5" placeholder="О чем хотите рассказать?" required></textarea>
                <small style="color: #666; display: block; margin-top: 5px;">
                    Запрещены: нецензурная лексика, политика, религия
                </small>
            </div>
            
            <div class="form-group">
                <label class="form-label">📁 Тип поста</label>
                <select name="post_type" class="form-input" required>
                    <option value="text">📝 Текстовый пост</option>
                    <option value="photo">🖼 Фото</option>
                    <option value="video">🎥 Видео</option>
                </select>
            </div>
            
            <div style="display: flex; gap: 15px; margin-top: 30px;">
                <button type="submit" class="btn">📤 Опубликовать</button>
                <a href="/feed" class="btn btn-secondary">← Назад к ленте</a>
            </div>
        </form>
    </div>'''
    
    return render_page('Создать пост', content)

@app.route('/delete_post/<int:post_id>')
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if post.user_id != current_user.id:
        flash('❌ Вы не можете удалить этот пост', 'error')
        return redirect('/feed')
    
    db.session.delete(post)
    db.session.commit()
    
    flash('✅ Пост удален', 'success')
    return redirect('/feed')

@app.route('/messages')
@login_required
def messages():
    # Получаем ID заблокированных пользователей
    blocked_ids = [b.blocked_id for b in BlockedUser.query.filter_by(blocker_id=current_user.id).all()]
    
    # Получаем диалоги только с незаблокированными пользователями
    sent_messages = Message.query.filter_by(sender_id=current_user.id).filter(~Message.receiver_id.in_(blocked_ids)).all()
    received_messages = Message.query.filter_by(receiver_id=current_user.id).filter(~Message.sender_id.in_(blocked_ids)).all()
    
    interlocutors = set()
    for msg in sent_messages:
        interlocutors.add(msg.receiver_id)
    for msg in received_messages:
        interlocutors.add(msg.sender_id)
    
    dialogues = []
    for user_id in interlocutors:
        if user_id != current_user.id:
            user = User.query.get(user_id)
            last_message = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
                ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
            ).order_by(Message.created_at.desc()).first()
            
            unread_count = Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id, is_read=False).count()
            
            dialogues.append({
                'user': user,
                'last_message': last_message,
                'unread_count': unread_count
            })
    
    dialogues.sort(key=lambda x: x['last_message'].created_at, reverse=True)
    
    dialogues_html = ""
    if dialogues:
        for dialogue in dialogues:
            last_msg = dialogue['last_message']
            is_sent_by_me = last_msg.sender_id == current_user.id
            dialogues_html += f'''<div class="user-card">
                <img src="/static/uploads/{dialogue['user'].avatar_filename}" class="user-avatar">
                <div class="user-name">{dialogue['user'].first_name} {dialogue['user'].last_name}</div>
                <small>@{dialogue['user'].username}</small>
                <div class="user-bio" style="font-size: 0.8em; color: #666; margin: 10px 0;">
                    {f'<strong>Вы:</strong> ' if is_sent_by_me else ''}{last_msg.content[:50]}{'...' if len(last_msg.content) > 50 else ''}
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <small>{last_msg.created_at.strftime('%d.%m.%Y %H:%M')}</small>
                    {f'<span class="unread-badge">{dialogue["unread_count"]}</span>' if dialogue['unread_count'] > 0 else ''}
                </div>
                <div style="margin-top: 10px; display: flex; gap: 5px;">
                    <a href="/send_message/{dialogue['user'].id}" class="btn btn-small">💬 Открыть чат</a>
                    <button onclick="confirmBlock({dialogue['user'].id}, '{dialogue['user'].username}')" class="btn btn-small btn-block">🚫 Заблокировать</button>
                </div>
            </div>'''
    else:
        dialogues_html = '<p style="text-align: center; color: #666; padding: 40px;">У вас пока нет сообщений.</p>'
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn active">💬 Сообщения</a>
        <a href="/users" class="nav-btn">👥 Пользователи</a>
        <a href="/profile/{current_user.id}" class="nav-btn">👤 Мой профиль</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #2a5298; margin-bottom: 20px;">💬 Мои сообщения</h2>
        
        <div class="user-list">
            {dialogues_html}
        </div>
    </div>'''
    
    return render_page('Сообщения', content)

@app.route('/send_message/<int:receiver_id>', methods=['GET', 'POST'])
@login_required
def send_message(receiver_id):
    receiver = User.query.get_or_404(receiver_id)
    
    if receiver_id == current_user.id:
        flash('❌ Нельзя отправить сообщение самому себе', 'error')
        return redirect('/messages')
    
    # Проверяем, не заблокирован ли получатель
    if is_user_blocked(current_user.id, receiver_id):
        flash('🚫 Этот пользователь заблокирован вами. Вы не можете писать ему сообщения.', 'error')
        return redirect('/messages')
    
    # Проверяем, не заблокировал ли нас получатель
    if is_user_blocked(receiver_id, current_user.id):
        flash('🚫 Этот пользователь заблокировал вас. Вы не можете писать ему сообщения.', 'error')
        return redirect('/messages')
    
    if request.method == 'POST':
        content = request.form['content']
        
        is_clean, found_words = check_content_for_report(content)
        
        if not is_clean:
            flash(f'⚠️ В вашем сообщении обнаружены слова, на которые могут пожаловаться: {", ".join(found_words)}. Вы все равно можете отправить сообщение, но будьте осторожны.', 'warning')
        
        new_message = Message(
            content=content,
            sender_id=current_user.id,
            receiver_id=receiver_id
        )
        
        db.session.add(new_message)
        db.session.commit()
        
        flash('✅ Сообщение отправлено!', 'success')
        return redirect(f'/send_message/{receiver_id}')
    
    messages_history = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == receiver_id)) |
        ((Message.sender_id == receiver_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()
    
    for msg in messages_history:
        if msg.receiver_id == current_user.id and not msg.is_read:
            msg.is_read = True
    db.session.commit()
    
    history_html = ""
    if messages_history:
        for msg in messages_history:
            is_sent = msg.sender_id == current_user.id
            history_html += f'''<div class="message {'sent' if is_sent else 'received'}{' hidden' if msg.is_hidden else ''}">
                <div class="message-header">
                    <span>{'Вы' if is_sent else receiver.first_name}</span>
                    <span>{msg.created_at.strftime('%d.%m.%Y %H:%M')}</span>
                </div>
                <div class="message-content">
                    {msg.content}
                    {f'<span class="warning-badge">⚠️ {msg.reports_count} жалоб</span>' if msg.reports_count > 0 else ''}
                    {f'<br><button onclick="confirmDelete(\'сообщение\', {msg.id})" class="btn btn-small btn-danger" style="margin-top: 5px; padding: 3px 8px; font-size: 12px;">🗑 Удалить</button>' if is_sent else ''}
                    {f'<br><button onclick="confirmReport(\'message\', {msg.id})" class="btn btn-small btn-report" style="margin-top: 5px; padding: 3px 8px; font-size: 12px;">🚩 Пожаловаться</button>' if not is_sent and not msg.is_hidden else ''}
                </div>
            </div>'''
    else:
        history_html = '<p style="text-align: center; color: #666; padding: 20px;">Нет сообщений. Начните диалог!</p>'
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/users" class="nav-btn">👥 Пользователи</a>
        <a href="/profile/{current_user.id}" class="nav-btn">👤 Мой профиль</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        {f'<a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Админ</a>' if current_user.is_admin else ''}
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <div style="display: flex; align-items: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 2px solid #eee;">
            <img src="/static/uploads/{receiver.avatar_filename}" class="avatar" alt="{receiver.username}">
            <div style="margin-left: 15px;">
                <h3 style="color: #2a5298; margin-bottom: 5px;">{receiver.first_name} {receiver.last_name}</h3>
                <p style="color: #666;">@{receiver.username}</p>
            </div>
            <div style="margin-left: auto; display: flex; gap: 10px;">
                <a href="/profile/{receiver.id}" class="btn btn-secondary">👤 Профиль</a>
                <button onclick="confirmBlock({receiver.id}, '{receiver.username}')" class="btn btn-block">🚫 Заблокировать</button>
            </div>
        </div>
        
        <div style="max-height: 400px; overflow-y: auto; padding: 15px; background: #f8f9fa; border-radius: 10px; margin-bottom: 25px;">
            {history_html}
        </div>
        
        <form method="POST" action="/send_message/{receiver_id}">
            <div class="form-group">
                <label class="form-label">💬 Новое сообщение</label>
                <textarea name="content" class="form-input" rows="3" placeholder="Введите сообщение..." required></textarea>
                <small style="color: #666; display: block; margin-top: 5px;">
                    Запрещены: нецензурная лексика, политика, религия
                </small>
            </div>
            
            <div style="display: flex; gap: 15px; margin-top: 20px;">
                <button type="submit" class="btn">📤 Отправить</button>
                <a href="/messages" class="btn btn-secondary">← Назад к диалогам</a>
            </div>
        </form>
    </div>'''
    
    return render_page(f'Чат с {receiver.first_name}', content)

@app.route('/delete_message/<int:message_id>')
@login_required
def delete_message(message_id):
    message = Message.query.get_or_404(message_id)
    
    if message.sender_id != current_user.id:
        flash('❌ Вы не можете удалить это сообщение', 'error')
        return redirect('/messages')
    
    receiver_id = message.receiver_id
    db.session.delete(message)
    db.session.commit()
    
    flash('✅ Сообщение удалено', 'success')
    return redirect(f'/send_message/{receiver_id}')

@app.route('/report/<item_type>/<int:item_id>')
@login_required
def report_content_route(item_type, item_id):
    """Маршрут для обработки жалоб"""
    success, message = report_content(item_type, item_id, current_user.id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    if item_type == 'post':
        return redirect('/feed')
    else:
        message_obj = Message.query.get(item_id)
        if message_obj:
            if current_user.id == message_obj.sender_id:
                return redirect(f'/send_message/{message_obj.receiver_id}')
            else:
                return redirect(f'/send_message/{message_obj.sender_id}')
        return redirect('/messages')

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
        <a href="/admin/users" class="nav-btn active" style="background: #6f42c1; border-color: #6f42c1;">👑 Управление пользователями</a>
        <a href="/admin/reports" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">📊 Жалобы</a>
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
    
    posts_html = ""
    if reported_posts:
        for post in reported_posts:
            author = User.query.get(post.user_id)
            posts_html += f'''<div class="post{' hidden' if post.is_hidden else ''}">
                <div class="post-header">
                    <img src="/static/uploads/{author.avatar_filename}" class="avatar avatar-small" alt="{author.username}">
                    <div>
                        <div class="post-author">{author.first_name} {author.last_name}</div>
                        <small>@{author.username}</small>
                    </div>
                    <div class="post-time">{post.created_at.strftime('%d.%m.%Y %H:%M')}</div>
                    <span class="warning-badge">⚠️ {post.reports_count} жалоб</span>
                </div>
                <div class="post-content">{post.content}</div>
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
                    {msg.content}
                    <span class="warning-badge">⚠️ {msg.reports_count} жалоб</span>
                </div>
                <div style="margin-top: 10px;">
                    <a href="/profile/{sender.id}" class="btn btn-small btn-secondary">👤 Профиль отправителя</a>
                    <button onclick="confirmBan({sender.id}, '{sender.username}')" class="btn btn-small btn-danger">🚫 Забанить отправителя</button>
                </div>
            </div>'''
    else:
        messages_html = '<p style="text-align: center; color: #666; padding: 20px;">Нет сообщений с жалобами.</p>'
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Пользователи</a>
        <a href="/admin/reports" class="nav-btn active" style="background: #6f42c1; border-color: #6f42c1;">📊 Жалобы</a>
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 20px;">📊 Модерация жалоб</h2>
        
        <h3 style="color: #2a5298; margin: 25px 0 15px 0;">📝 Посты с жалобами</h3>
        {posts_html}
        
        <h3 style="color: #2a5298; margin: 25px 0 15px 0;">💬 Сообщения с жалобами</h3>
        {messages_html}
    </div>'''
    
    return render_page('Админ-панель - Жалобы', content)

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
    
    # Удаляем блокировки пользователя
    BlockedUser.query.filter_by(blocker_id=user_id).delete()
    BlockedUser.query.filter_by(blocked_id=user_id).delete()
    
    # Удаляем пользователя
    db.session.delete(user)
    db.session.commit()
    
    flash(f'✅ Аккаунт пользователя {username} удален', 'success')
    return redirect('/admin/users')

@app.route('/users')
@login_required
def users():
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
                    <a href="/send_message/{user.id}" class="btn btn-small btn-success">💬 Написать</a>
                    <button onclick="confirmBlock({user.id}, '{user.username}')" class="btn btn-small btn-block">🚫 Заблокировать</button>
                </div>
            </div>'''
    else:
        users_html = '<p style="text-align: center; color: #666; padding: 40px;">Пользователи не найдены.</p>'
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения</a>
        <a href="/users" class="nav-btn active">👥 Пользователи</a>
        <a href="/profile/{current_user.id}" class="nav-btn">👤 Мой профиль</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
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

@app.route('/test_email')
def test_email():
    """Тестирование отправки email"""
    try:
        success = send_verification_email(
            'test@example.com',
            '123456',
            'Test User'
        )
        if success:
            return '✅ Email отправлен успешно!'
        else:
            return '❌ Ошибка отправки email'
    except Exception as e:
        return f'❌ Ошибка: {str(e)}'

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
    print("   2. 🚫 Блокировка пользователей (обычными пользователями)")
    print("   3. 👮 Баны и удаление аккаунтов (администратором)")
    print("   4. 📊 Система жалоб и модерации")
    print("   5. 💬 Личные сообщения с фильтрацией заблокированных")
    print("="*60)
    
    app.run(debug=True, port=5000, use_reloader=False)
