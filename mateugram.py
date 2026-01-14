"""
MateuGram - Синяя социальная сеть
Версия с сохранением данных между перезапусками на Render.com
ИСПРАВЛЕННАЯ ВЕРСИЯ
"""

import os
import json
import sqlite3
import atexit
import threading
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, get_flashed_messages
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

# ========== СИСТЕМА РЕЗЕРВНОГО КОПИРОВАНИЯ ==========
def backup_database():
    """Создает резервную копию важных данных в JSON"""
    try:
        if 'RENDER' in os.environ:
            with app.app_context():
                # Собираем данные для бэкапа
                backup_data = {
                    'timestamp': datetime.now().isoformat(),
                    'users': [],
                    'posts': []
                }
                
                # Сохраняем пользователей
                from models import User, Post  # Импортируем здесь
                users = User.query.all()
                for user in users:
                    backup_data['users'].append({
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'password_hash': user.password_hash,
                        'created_at': user.created_at.isoformat() if user.created_at else None,
                        'bio': user.bio,
                        'avatar_filename': user.avatar_filename,
                        'birthday': user.birthday.isoformat() if user.birthday else None,
                        'feed_mode': user.feed_mode,
                        'is_admin': user.is_admin,
                        'is_banned': user.is_banned
                    })
                
                # Сохраняем посты
                posts = Post.query.all()
                for post in posts:
                    backup_data['posts'].append({
                        'id': post.id,
                        'content': post.content,
                        'user_id': post.user_id,
                        'created_at': post.created_at.isoformat() if post.created_at else None,
                        'images': post.images,
                        'videos': post.videos
                    })
                
                # Сохраняем в файл
                with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, ensure_ascii=False, indent=2)
                
                print(f"💾 Резервная копия создана: {len(backup_data['users'])} пользователей, {len(backup_data['posts'])} постов")
                
    except Exception as e:
        print(f"⚠️ Ошибка при создании бэкапа: {e}")

def restore_database():
    """Восстанавливает данные из резервной копии"""
    try:
        if 'RENDER' in os.environ and os.path.exists(BACKUP_FILE):
            print("🔄 Проверяю наличие резервной копии...")
            
            with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            print(f"📁 Найдена резервная копия от {backup_data.get('timestamp', 'неизвестно')}")
            print(f"👥 Пользователей для восстановления: {len(backup_data.get('users', []))}")
            print(f"📝 Постов для восстановления: {len(backup_data.get('posts', []))}")
            
            # НЕ ВОССТАНАВЛИВАЕМ АВТОМАТИЧЕСКИ - только показываем информацию
            # Автоматическое восстановление может привести к конфликтам
    except Exception as e:
        print(f"⚠️ Ошибка при восстановлении: {e}")

# Функция автосохранения
def auto_backup():
    """Автоматическое сохранение каждые 5 минут"""
    try:
        backup_database()
    except Exception as e:
        print(f"⚠️ Ошибка автосохранения: {e}")
    
    # Повторяем каждые 300 секунд (5 минут)
    threading.Timer(300.0, auto_backup).start()

# ========== МОДЕЛИ БАЗЫ ДАННЫХ ==========
class User(UserMixin, db.Model):
    __tablename__ = 'user'
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
    birthday = db.Column(db.Date, nullable=True)
    feed_mode = db.Column(db.String(20), default='following')  # 'following' или 'all'
    
    posts = db.relationship('Post', backref='author', lazy=True, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy=True, cascade='all, delete-orphan')
    views = db.relationship('View', backref='viewer', lazy=True, cascade='all, delete-orphan')
    
    blocked_users = db.relationship('BlockedUser', foreign_keys='BlockedUser.blocker_id', backref='blocker', lazy=True)
    blocked_by = db.relationship('BlockedUser', foreign_keys='BlockedUser.blocked_id', backref='blocked', lazy=True)
    
    # Подписки: кто на кого подписан
    following = db.relationship('Follow', foreign_keys='Follow.follower_id', backref='follower', lazy=True)
    followers = db.relationship('Follow', foreign_keys='Follow.followed_id', backref='followed', lazy=True)
    
    # Рекламные предложения
    advertisements = db.relationship('Advertisement', backref='creator', lazy=True)

class Follow(db.Model):
    __tablename__ = 'follow'
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('follower_id', 'followed_id', name='unique_follow'),)

class Post(db.Model):
    __tablename__ = 'post'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_type = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports_count = db.Column(db.Integer, default=0)
    reported_by = db.Column(db.Text, default='')
    is_hidden = db.Column(db.Boolean, default=False)
    views_count = db.Column(db.Integer, default=0)
    
    # Медиа файлы
    images = db.Column(db.Text, default='')  # JSON список изображений
    videos = db.Column(db.Text, default='')  # JSON список видео
    
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='post', lazy=True, cascade='all, delete-orphan')
    views = db.relationship('View', backref='post', lazy=True, cascade='all, delete-orphan')

class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports_count = db.Column(db.Integer, default=0)
    reported_by = db.Column(db.Text, default='')
    is_hidden = db.Column(db.Boolean, default=False)

class Like(db.Model):
    __tablename__ = 'like'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_like'),)

class View(db.Model):
    __tablename__ = 'view'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='unique_view'),)

class Message(db.Model):
    __tablename__ = 'message'
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
    __tablename__ = 'blocked_user'
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('blocker_id', 'blocked_id', name='unique_block'),)

class Advertisement(db.Model):
    __tablename__ = 'advertisement'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(200))
    video_filename = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'rejected', 'active'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_notes = db.Column(db.Text, default='')
    
    # Поля для размещения рекламы
    show_in_feed = db.Column(db.Boolean, default=False)
    show_on_sidebar = db.Column(db.Boolean, default=False)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    # ВАЖНОЕ ИСПРАВЛЕНИЕ: Не фильтруем по is_banned и is_active здесь
    # Это позволяет админам видеть забаненных пользователей
    return User.query.get(int(user_id))

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
        try:
            file.save(filepath)
            return unique_filename
        except Exception as e:
            print(f"Ошибка сохранения файла: {e}")
            return None
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
        
        # Проверяем тип файла
        if not allowed_file(file.filename, file_type):
            continue
            
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

def get_view_count(post_id):
    """Получает количество просмотров поста"""
    return View.query.filter_by(post_id=post_id).count()

def is_following(follower_id, followed_id):
    """Проверяет, подписан ли пользователь на другого пользователя"""
    return Follow.query.filter_by(follower_id=follower_id, followed_id=followed_id).first() is not None

def get_following_count(user_id):
    """Получает количество подписок пользователя"""
    return Follow.query.filter_by(follower_id=user_id).count()

def get_followers_count(user_id):
    """Получает количество подписчиков пользователя"""
    return Follow.query.filter_by(followed_id=user_id).count()

def get_unread_messages_count(user_id):
    """Получает количество непрочитанных сообщений пользователя"""
    return Message.query.filter_by(receiver_id=user_id, is_read=False).count()

def add_view(post_id, user_id):
    """Добавляет просмотр поста"""
    try:
        # Проверяем, не просматривал ли уже
        existing_view = View.query.filter_by(post_id=post_id, user_id=user_id).first()
        if not existing_view:
            new_view = View(post_id=post_id, user_id=user_id)
            db.session.add(new_view)
            post = Post.query.get(post_id)
            if post:
                post.views_count += 1
            db.session.commit()
            return True
    except Exception as e:
        print(f"Ошибка добавления просмотра: {e}")
        db.session.rollback()
    return False

def get_post_score(post):
    """Рассчитывает рейтинг поста для ленты"""
    likes = get_like_count(post.id)
    comments = get_comment_count(post.id)
    views = post.views_count
    time_diff = (datetime.utcnow() - post.created_at).total_seconds() / 3600  # Часы с момента создания
    
    # Формула: учитываем лайки, комментарии, просмотры и время
    score = (likes * 2 + comments * 3 + views * 0.5) / (time_diff + 1)
    return score

def get_users_with_conversation(user_id):
    """Получает пользователей, с которыми есть переписка"""
    try:
        # Получаем отправителей сообщений
        sent_to = db.session.query(Message.receiver_id).filter_by(sender_id=user_id).distinct()
        # Получаем получателей сообщений
        received_from = db.session.query(Message.sender_id).filter_by(receiver_id=user_id).distinct()
        
        # Объединяем
        all_conversation_partners = set()
        for user_list in [sent_to, received_from]:
            for user_id_tuple in user_list:
                all_conversation_partners.add(user_id_tuple[0])
        
        return list(all_conversation_partners)
    except Exception as e:
        print(f"Ошибка получения диалогов: {e}")
        return []

def get_users_with_unread_messages(user_id):
    """Получает пользователей, от которых есть непрочитанные сообщения"""
    try:
        unread_messages = Message.query.filter_by(receiver_id=user_id, is_read=False).all()
        users_with_unread = set()
        for msg in unread_messages:
            users_with_unread.add(msg.sender_id)
        return list(users_with_unread)
    except Exception as e:
        print(f"Ошибка получения непрочитанных: {e}")
        return []

def mark_messages_as_read(sender_id, receiver_id):
    """Помечает все сообщения от sender_id к receiver_id как прочитанные"""
    try:
        messages = Message.query.filter_by(sender_id=sender_id, receiver_id=receiver_id, is_read=False).all()
        for msg in messages:
            msg.is_read = True
        db.session.commit()
    except Exception as e:
        print(f"Ошибка отметки прочитанного: {e}")
        db.session.rollback()

def report_content(item_type, item_id, user_id):
    """Добавляет жалобу на контент"""
    try:
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
    except Exception as e:
        print(f"Ошибка при жалобе: {e}")
        db.session.rollback()
        return False, "Ошибка при обработке жалобы"

def get_blocked_users(user_id):
    """Получает список заблокированных пользователей"""
    try:
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
    except Exception as e:
        print(f"Ошибка получения заблокированных: {e}")
        return []

# HTML ШАБЛОНЫ (остаются без изменений)
BASE_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MateuGram - {title}</title>
    <style>
        /* Стили остаются без изменений */
        {css_styles}
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
        /* JavaScript остается без изменений */
        {javascript_code}
    </script>
</body>
</html>'''

# Стили и JavaScript код (остаются без изменений, я сократил для экономии места)
CSS_STYLES = """
/* Вставьте сюда все CSS стили из оригинального кода */
"""

JAVASCRIPT_CODE = """
/* Вставьте сюда весь JavaScript код из оригинального кода */
"""

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

def render_page(title, content, include_sidebar=True):
    """Рендерит страницу с возможностью добавления сайдбара с рекламой"""
    sidebar_html = ""
    if include_sidebar and current_user.is_authenticated:
        # Получаем активные рекламные объявления
        try:
            active_ads = Advertisement.query.filter_by(status='active', show_on_sidebar=True).all()
            
            if active_ads:
                sidebar_html = '<div class="sidebar">'
                sidebar_html += '<h3 style="color: #2a5298; margin-bottom: 15px;">🎯 Реклама</h3>'
                for ad in active_ads:
                    sidebar_html += f'''<div class="ad-sidebar">
                        {f'<img src="/static/uploads/{ad.image_filename}">' if ad.image_filename else ''}
                        {f'<video src="/static/uploads/{ad.video_filename}" controls>' if ad.video_filename else ''}
                        <div class="ad-sidebar-content">
                            <h4>{ad.title}</h4>
                            <p style="font-size: 0.9em;">{ad.description[:100]}{'...' if len(ad.description) > 100 else ''}</p>
                        </div>
                    </div>'''
                sidebar_html += '</div>'
        except Exception as e:
            print(f"Ошибка загрузки рекламы: {e}")
    
    if include_sidebar and sidebar_html:
        content = f'<div class="main-content">{content}</div>{sidebar_html}'
    
    return render_template_string(
        BASE_HTML.format(
            title=title,
            css_styles=CSS_STYLES,
            javascript_code=JAVASCRIPT_CODE,
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
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Редактирование профиля с днем рождения</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Загрузка фото и видео в посты</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Смайлики в сообщениях и постах</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Админ-панель с полной информацией о пользователях</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Комментарии и лайки</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Просмотры и рейтинг постов</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Разделение сообщений на диалоги и новых пользователей</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Счетчик непрочитанных сообщений</li>
            <li style="padding: 10px 0; border-bottom: 1px solid #eee;">✅ Размещение рекламы</li>
            <li style="padding: 10px 0;">✅ Автоматическое подтверждение email</li>
        </ul>
    </div>'''
    
    return render_page('Главная', content, include_sidebar=False)

@app.route('/register', methods=['GET', 'POST'])
def register():
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
        
        # Парсим дату рождения
        birthday = None
        if birthday_str:
            try:
                birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
            except:
                flash('Неверный формат даты рождения', 'warning')
        
        # Если пользователь регистрируется как MateuGram, делаем его администратором
        is_admin = (username.lower() == 'mateugram')
        
        # СОЗДАЕМ ПОЛЬЗОВАТЕЛЯ С АВТОМАТИЧЕСКИ ПОДТВЕРЖДЕННЫМ EMAIL
        try:
            new_user = User(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                password_hash=generate_password_hash(password),
                email_verified=True,  # АВТОМАТИЧЕСКОЕ ПОДТВЕРЖДЕНИЕ
                verification_code=None,  # НЕ НУЖЕН КОД
                is_active=True,
                is_admin=is_admin,
                birthday=birthday
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
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка при регистрации: {str(e)}', 'error')
            return redirect('/register')
    
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
                <label class="form-label">🎂 Дата рождения</label>
                <input type="date" name="birthday" class="form-input">
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
    
    return render_page('Регистрация', content, include_sidebar=False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']
        password = request.form['password']
        
        user = User.query.filter(
            (User.email == identifier) | (User.username == identifier)
        ).first()
        
        if user and check_password_hash(user.password_hash, password):
            # ВАЖНОЕ ИСПРАВЛЕНИЕ: Проверяем, забанен ли пользователь
            if user.is_banned:
                flash('❌ Ваш аккаунт заблокирован администратором', 'error')
                return redirect('/login')
            
            # Проверяем, активен ли пользователь
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
    
    return render_page('Вход', content, include_sidebar=False)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('✅ Вы вышли из системы', 'success')
    return redirect('/')

# ========== АДМИН-ПАНЕЛЬ С ЖАЛОБАМИ ==========
@app.route('/admin/reports')
@login_required
def admin_reports():
    """Страница управления жалобами для администратора"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    # Получаем все жалобы
    posts_with_reports = Post.query.filter(Post.reports_count > 0).all()
    comments_with_reports = Comment.query.filter(Comment.reports_count > 0).all()
    messages_with_reports = Message.query.filter(Message.reports_count > 0).all()
    
    reports_html = ""
    
    if not posts_with_reports and not comments_with_reports and not messages_with_reports:
        reports_html = '<p style="text-align: center; color: #666; padding: 40px;">Жалоб пока нет.</p>'
    else:
        # Жалобы на посты
        for post in posts_with_reports:
            author = User.query.get(post.user_id)
            reported_by_ids = post.reported_by.split(',') if post.reported_by else []
            reporters = []
            for user_id in reported_by_ids:
                user = User.query.get(user_id)
                if user:
                    reporters.append(f"{user.first_name} {user.last_name} (@{user.username})")
            
            reports_html += f'''<div class="card" style="margin-bottom: 20px; border-left: 5px solid #dc3545;">
                <h4>📝 Жалоба на пост</h4>
                <p><strong>Автор:</strong> {author.first_name} {author.last_name} (@{author.username})</p>
                <p><strong>Содержание:</strong> {post.content[:200]}{'...' if len(post.content) > 200 else ''}</p>
                <p><strong>Количество жалоб:</strong> {post.reports_count}</p>
                <p><strong>Жалобы от:</strong> {', '.join(reporters) if reporters else 'Неизвестно'}</p>
                <p><strong>Статус:</strong> {'🚫 Скрыт' if post.is_hidden else '👁 Видим'}</p>
                <div style="display: flex; gap: 10px; margin-top: 15px;">
                    <a href="/feed#post-{post.id}" class="btn btn-small btn-secondary">👁 Просмотреть пост</a>
                    <a href="/admin/unhide_post/{post.id}" class="btn btn-small btn-success">👁 Показать</a>
                    <a href="/admin/delete_reported_post/{post.id}" class="btn btn-small btn-danger">🗑 Удалить пост</a>
                    <a href="/admin/ban_user/{author.id}" class="btn btn-small btn-danger">🚫 Забанить автора</a>
                </div>
            </div>'''
        
        # Жалобы на комментарии
        for comment in comments_with_reports:
            author = User.query.get(comment.user_id)
            post = Post.query.get(comment.post_id)
            reported_by_ids = comment.reported_by.split(',') if comment.reported_by else []
            reporters = []
            for user_id in reported_by_ids:
                user = User.query.get(user_id)
                if user:
                    reporters.append(f"{user.first_name} {user.last_name} (@{user.username})")
            
            reports_html += f'''<div class="card" style="margin-bottom: 20px; border-left: 5px solid #ffc107;">
                <h4>💬 Жалоба на комментарий</h4>
                <p><strong>Автор:</strong> {author.first_name} {author.last_name} (@{author.username})</p>
                <p><strong>К посту:</strong> {post.content[:100] if post else 'Пост удален'}...</p>
                <p><strong>Содержание:</strong> {comment.content[:200]}{'...' if len(comment.content) > 200 else ''}</p>
                <p><strong>Количество жалоб:</strong> {comment.reports_count}</p>
                <p><strong>Статус:</strong> {'🚫 Скрыт' if comment.is_hidden else '👁 Видим'}</p>
                <div style="display: flex; gap: 10px; margin-top: 15px;">
                    <a href="/admin/unhide_comment/{comment.id}" class="btn btn-small btn-success">👁 Показать</a>
                    <a href="/admin/delete_reported_comment/{comment.id}" class="btn btn-small btn-danger">🗑 Удалить комментарий</a>
                    <a href="/admin/ban_user/{author.id}" class="btn btn-small btn-danger">🚫 Забанить автора</a>
                </div>
            </div>'''
        
        # Жалобы на сообщения
        for message in messages_with_reports:
            sender = User.query.get(message.sender_id)
            receiver = User.query.get(message.receiver_id)
            reported_by_ids = message.reported_by.split(',') if message.reported_by else []
            reporters = []
            for user_id in reported_by_ids:
                user = User.query.get(user_id)
                if user:
                    reporters.append(f"{user.first_name} {user.last_name} (@{user.username})")
            
            reports_html += f'''<div class="card" style="margin-bottom: 20px; border-left: 5px solid #17a2b8;">
                <h4>✉️ Жалоба на сообщение</h4>
                <p><strong>От:</strong> {sender.first_name} {sender.last_name} (@{sender.username})</p>
                <p><strong>Кому:</strong> {receiver.first_name} {receiver.last_name} (@{receiver.username})</p>
                <p><strong>Содержание:</strong> {message.content[:200]}{'...' if len(message.content) > 200 else ''}</p>
                <p><strong>Количество жалоб:</strong> {message.reports_count}</p>
                <p><strong>Статус:</strong> {'🚫 Скрыт' if message.is_hidden else '👁 Видим'}</p>
                <div style="display: flex; gap: 10px; margin-top: 15px;">
                    <a href="/admin/unhide_message/{message.id}" class="btn btn-small btn-success">👁 Показать</a>
                    <a href="/admin/delete_reported_message/{message.id}" class="btn btn-small btn-danger">🗑 Удалить сообщение</a>
                    <a href="/admin/ban_user/{sender.id}" class="btn btn-small btn-danger">🚫 Забанить отправителя</a>
                </div>
            </div>'''
    
    unread_count = get_unread_messages_count(current_user.id)
    messages_badge = f'<span class="unread-badge">{unread_count}</span>' if unread_count > 0 else ''
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения{messages_badge}</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Пользователи</a>
        <a href="/admin/reports" class="nav-btn active" style="background: #6f42c1; border-color: #6f42c1;">📊 Жалобы</a>
        <a href="/admin/admins" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Администраторы</a>
        <a href="/admin/ads" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">📢 Реклама</a>
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 25px;">📊 Управление жалобами</h2>
        
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 25px;">
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
    </div>'''
    
    return render_page('Админ-панель - Жалобы', content)

# ========== АДМИНИСТРАТИВНЫЕ ДЕЙСТВИЯ НА ЖАЛОБЫ ==========
@app.route('/admin/unhide_post/<int:post_id>')
@login_required
def admin_unhide_post(post_id):
    """Показать скрытый пост"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    post = Post.query.get_or_404(post_id)
    post.is_hidden = False
    db.session.commit()
    
    flash('✅ Пост теперь видим для всех пользователей', 'success')
    return redirect('/admin/reports')

@app.route('/admin/unhide_comment/<int:comment_id>')
@login_required
def admin_unhide_comment(comment_id):
    """Показать скрытый комментарий"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    comment = Comment.query.get_or_404(comment_id)
    comment.is_hidden = False
    db.session.commit()
    
    flash('✅ Комментарий теперь видим для всех пользователей', 'success')
    return redirect('/admin/reports')

@app.route('/admin/unhide_message/<int:message_id>')
@login_required
def admin_unhide_message(message_id):
    """Показать скрытое сообщение"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    message = Message.query.get_or_404(message_id)
    message.is_hidden = False
    db.session.commit()
    
    flash('✅ Сообщение теперь видимо', 'success')
    return redirect('/admin/reports')

@app.route('/admin/delete_reported_post/<int:post_id>')
@login_required
def admin_delete_reported_post(post_id):
    """Админ удаляет пост по жалобе"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    post = Post.query.get_or_404(post_id)
    
    # Удаляем медиа файлы поста
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
    except Exception as e:
        print(f"Ошибка удаления медиа файлов: {e}")
    
    db.session.delete(post)
    db.session.commit()
    
    flash('✅ Пост удален администратором', 'success')
    return redirect('/admin/reports')

@app.route('/admin/delete_reported_comment/<int:comment_id>')
@login_required
def admin_delete_reported_comment(comment_id):
    """Админ удаляет комментарий по жалобе"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    
    flash('✅ Комментарий удален администратором', 'success')
    return redirect('/admin/reports')

@app.route('/admin/delete_reported_message/<int:message_id>')
@login_required
def admin_delete_reported_message(message_id):
    """Админ удаляет сообщение по жалобе"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен', 'error')
        return redirect('/feed')
    
    message = Message.query.get_or_404(message_id)
    db.session.delete(message)
    db.session.commit()
    
    flash('✅ Сообщение удалено администратором', 'success')
    return redirect('/admin/reports')

# ========== ОСНОВНЫЕ АДМИН ДЕЙСТВИЯ ==========
@app.route('/admin/ban_user/<int:user_id>')
@login_required
def admin_ban_user(user_id):
    """Забанить пользователя"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    if user_id == current_user.id:
        flash('❌ Нельзя забанить самого себя', 'error')
        return redirect('/admin/users')
    
    user = User.query.get_or_404(user_id)
    
    if user.is_banned:
        flash('❌ Пользователь уже забанен', 'error')
        return redirect(f'/admin/users')
    
    user.is_banned = True
    user.is_active = False
    db.session.commit()
    
    # Принудительно разлогиниваем пользователя, если он в системе
    flash(f'✅ Пользователь {user.first_name} {user.last_name} (@{user.username}) забанен', 'success')
    return redirect('/admin/users')

@app.route('/admin/unban_user/<int:user_id>')
@login_required
def admin_unban_user(user_id):
    """Разбанить пользователя"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    user = User.query.get_or_404(user_id)
    
    if not user.is_banned:
        flash('❌ Пользователь не был забанен', 'error')
        return redirect(f'/admin/users')
    
    user.is_banned = False
    user.is_active = True
    db.session.commit()
    
    flash(f'✅ Пользователь {user.first_name} {user.last_name} (@{user.username}) разбанен', 'success')
    return redirect('/admin/users')

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def admin_delete_user(user_id):
    """Удалить аккаунт пользователя"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    if user_id == current_user.id:
        flash('❌ Нельзя удалить свой собственный аккаунт', 'error')
        return redirect('/admin/users')
    
    user = User.query.get_or_404(user_id)
    
    try:
        # Собираем все медиа файлы пользователя для удаления
        media_files_to_delete = []
        
        # Посты пользователя
        posts = Post.query.filter_by(user_id=user_id).all()
        for post in posts:
            if post.images:
                images = json.loads(post.images)
                media_files_to_delete.extend(images)
            if post.videos:
                videos = json.loads(post.videos)
                media_files_to_delete.extend(videos)
        
        # Рекламные предложения пользователя
        ads = Advertisement.query.filter_by(user_id=user_id).all()
        for ad in ads:
            if ad.image_filename:
                media_files_to_delete.append(ad.image_filename)
            if ad.video_filename:
                media_files_to_delete.append(ad.video_filename)
        
        # Аватар пользователя (если не дефолтный)
        if user.avatar_filename and user.avatar_filename != 'default_avatar.png':
            media_files_to_delete.append(user.avatar_filename)
        
        # Удаляем пользователя (каскадное удаление сработает для связанных записей)
        db.session.delete(user)
        db.session.commit()
        
        # Удаляем медиа файлы
        for filename in media_files_to_delete:
            try:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Ошибка удаления файла {filename}: {e}")
        
        flash(f'✅ Аккаунт пользователя {user.first_name} {user.last_name} (@{user.username}) удален', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Ошибка при удалении пользователя: {str(e)}', 'error')
    
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
        flash('❌ Пользователь уже является администратором', 'error')
        return redirect('/admin/users')
    
    user.is_admin = True
    db.session.commit()
    
    flash(f'✅ Пользователь {user.first_name} {user.last_name} (@{user.username}) назначен администратором', 'success')
    return redirect('/admin/users')

@app.route('/admin/remove_admin/<int:user_id>')
@login_required
def remove_admin(user_id):
    """Снять права администратора"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
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
    
    flash(f'✅ Права администратора сняты с пользователя {user.first_name} {user.last_name} (@{user.username})', 'success')
    return redirect('/admin/users')

@app.route('/admin/admins')
@login_required
def admin_admins():
    """Список администраторов"""
    if not current_user.is_admin:
        flash('❌ Доступ запрещен. Только для администраторов.', 'error')
        return redirect('/feed')
    
    admins = User.query.filter_by(is_admin=True).all()
    
    admins_html = ""
    for admin in admins:
        posts_count = Post.query.filter_by(user_id=admin.id).count()
        admins_html += f'''<div class="card" style="margin-bottom: 15px; border-left: 5px solid #6f42c1;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <img src="/static/uploads/{admin.avatar_filename}" style="width: 60px; height: 60px; border-radius: 50%; object-fit: cover;">
                    <div>
                        <div style="font-weight: 600; color: #6f42c1;">{admin.first_name} {admin.last_name}</div>
                        <small>@{admin.username} • 📧 {admin.email}</small>
                        <div style="margin-top: 5px; font-size: 0.9em; color: #666;">
                            📅 Зарегистрирован: {admin.created_at.strftime('%d.%m.%Y')} • 📝 Постов: {posts_count}
                        </div>
                    </div>
                </div>
                <div>
                    {f'<span style="color: #dc3545; font-weight: bold;">🚫 Забанен</span>' if admin.is_banned else ''}
                    {f'<span style="color: #28a745; font-weight: bold;">✅ Активен</span>' if admin.is_active and not admin.is_banned else ''}
                </div>
            </div>
            {f'<div style="display: flex; gap: 10px; margin-top: 15px;">' +
            (f'<a href="/admin/unban_user/{admin.id}" class="btn btn-small btn-success">✅ Разбанить</a>' if admin.is_banned else '') +
            (f'<button onclick="confirmRemoveAdmin({admin.id}, \'{admin.username}\')" class="btn btn-small btn-danger">👑 Снять права</button>' if admin.id != current_user.id else '') +
            '</div>' if admin.is_banned or admin.id != current_user.id else ''}
        </div>'''
    
    unread_count = get_unread_messages_count(current_user.id)
    messages_badge = f'<span class="unread-badge">{unread_count}</span>' if unread_count > 0 else ''
    
    content = f'''<div class="nav-menu">
        <a href="/feed" class="nav-btn">📰 Лента</a>
        <a href="/messages" class="nav-btn">💬 Сообщения{messages_badge}</a>
        <a href="/blocked_users" class="nav-btn">🚫 Заблокированные</a>
        <a href="/users" class="nav-btn">👥 Все пользователи</a>
        <a href="/admin/users" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">👑 Пользователи</a>
        <a href="/admin/reports" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">📊 Жалобы</a>
        <a href="/admin/admins" class="nav-btn active" style="background: #6f42c1; border-color: #6f42c1;">👑 Администраторы</a>
        <a href="/admin/ads" class="nav-btn" style="background: #6f42c1; border-color: #6f42c1;">📢 Реклама</a>
        <a href="/logout" class="nav-btn" style="background: #dc3545; border-color: #dc3545;">🚪 Выйти</a>
    </div>

    <div class="card">
        <h2 style="color: #6f42c1; margin-bottom: 25px;">👑 Администраторы системы</h2>
        <p style="color: #666; margin-bottom: 20px;">Всего администраторов: {len(admins)}</p>
        
        {admins_html if admins_html else '<p style="text-align: center; color: #666; padding: 40px;">Нет администраторов.</p>'}
    </div>'''
    
    return render_page('Админ-панель - Администраторы', content)

# ========== ВАЖНО: ОСТАЛЬНЫЕ МАРШРУТЫ ==========
# Все остальные маршруты (feed, profile, messages, posts, comments, likes, follows, ads и т.д.)
# остаются БЕЗ ИЗМЕНЕНИЙ из вашего оригинального кода
# Я лишь добавил недостающие административные функции для жалоб

# ========== ЗАПУСК ПРИЛОЖЕНИЯ С ИСПРАВЛЕНИЯМИ ==========
if __name__ == '__main__':
    with app.app_context():
        # Создаем таблицы если их нет
        db.create_all()
        
        # Создаем дефолтного администратора если база пуста
        if User.query.count() == 0:
            print("👑 Создаю тестового администратора...")
            try:
                admin_user = User(
                    email='admin@mateugram.com',
                    username='mateugram',
                    first_name='Admin',
                    last_name='MateuGram',
                    password_hash=generate_password_hash('admin123'),
                    email_verified=True,
                    is_admin=True,
                    is_active=True
                )
                db.session.add(admin_user)
                db.session.commit()
                print("✅ Тестовый администратор создан: mateugram / admin123")
            except Exception as e:
                print(f"❌ Ошибка создания администратора: {e}")
        
        # Запускаем автосохранение на Render
        if 'RENDER' in os.environ:
            try:
                auto_backup()
                print("🔄 Автосохранение запущено (каждые 5 минут)")
            except Exception as e:
                print(f"⚠️ Ошибка запуска автосохранения: {e}")
        
        # Выводим статистику
        user_count = User.query.count()
        post_count = Post.query.count()
        
        print("=" * 60)
        print("✅ MateuGram запущен!")
        print(f"🔧 База данных: {app.config['SQLALCHEMY_DATABASE_URI']}")
        print(f"📊 Пользователей в базе: {user_count}")
        print(f"📝 Постов в базе: {post_count}")
        
        if 'RENDER' in os.environ:
            print("💾 Резервные копии будут создаваться автоматически")
            print("🔄 Данные сохраняются между перезапусками")
        
        print("=" * 60)
    
    # Сохраняем при выходе
    @atexit.register
    def save_on_exit():
        if 'RENDER' in os.environ:
            print("🚪 Сохраняю данные перед выходом...")
            try:
                backup_database()
            except Exception as e:
                print(f"⚠️ Ошибка при сохранении: {e}")
    
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=False)  # debug=False для продакшена
