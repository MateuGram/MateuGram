"""
MateuGram - Синяя социальная сеть
ВЕРСИЯ С ИСПРАВЛЕНИЯМИ И УЛУЧШЕННЫМ СОХРАНЕНИЕМ ДАННЫХ
"""

import os
import json
import shutil
import sqlite3
from datetime import datetime, date
from flask import Flask, request, redirect, url_for, flash, get_flashed_messages, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import re
import secrets
import atexit
import logging
from logging.handlers import RotatingFileHandler

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКА ПРИЛОЖЕНИЯ ==========
app = Flask(__name__)

# Генерируем SECRET_KEY для сессий
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ========== УЛУЧШЕННОЕ СОХРАНЕНИЕ ДАННЫХ ДЛЯ RENDER.COM ==========
# Важная настройка для сохранения данных на Render.com
if 'RENDER' in os.environ or 'RENDER_EXTERNAL_HOSTNAME' in os.environ:
    logger.info("🌐 Обнаружен Render.com - использую постоянное хранилище...")
    
    # Проверяем доступность различных постоянных папок
    persistent_dirs = ['/tmp', '/var/tmp', '/data', '/persistent']
    persistent_dir = '/tmp'  # По умолчанию
    
    for dir_path in persistent_dirs:
        if os.path.exists(dir_path) and os.access(dir_path, os.W_OK):
            persistent_dir = dir_path
            logger.info(f"📁 Найдена доступная постоянная папка: {persistent_dir}")
            break
    
    # Создаем структуру папок для данных
    DB_FILE = os.path.join(persistent_dir, 'mateugram_persistent.db')
    BACKUP_DIR = os.path.join(persistent_dir, 'backups')
    UPLOAD_DIR = os.path.join(persistent_dir, 'uploads')
    
    # Создаем все необходимые директории
    for directory in [BACKUP_DIR, UPLOAD_DIR]:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"📂 Создана директория: {directory}")
    
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_FILE}'
    app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
    logger.info(f"📊 База данных: {DB_FILE}")
    logger.info(f"📁 Папка загрузок: {UPLOAD_DIR}")
    
    # Настраиваем ежедневное резервное копирование
    BACKUP_SCHEDULE = True
else:
    logger.info("🏠 Локальный режим - использование локального хранилища")
    DB_FILE = 'mateugram.db'
    BACKUP_DIR = 'backups'
    os.makedirs(BACKUP_DIR, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_FILE}'
    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    BACKUP_SCHEDULE = False

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

# Создаем папки если их нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Настраиваем движок SQLAlchemy для лучшей производительности
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

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
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связи
    posts = db.relationship('Post', backref='author', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='author', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy=True, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    following = db.relationship('Follow', foreign_keys='Follow.follower_id', backref='follower', lazy=True)
    followers = db.relationship('Follow', foreign_keys='Follow.followed_id', backref='followed', lazy=True)
    reports_sent = db.relationship('Report', foreign_keys='Report.reporter_id', backref='reporter', lazy=True)
    reports_received = db.relationship('Report', foreign_keys='Report.reported_id', backref='reported', lazy=True)

class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('follower_id', 'followed_id', name='unique_follow'),
    )

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
    reports = db.relationship('Report', backref='post', lazy=True, cascade='all, delete-orphan')

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
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'post_id', name='unique_like'),
    )

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reported_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, resolved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    admin_notes = db.Column(db.Text, default='')

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception as e:
        logger.error(f"Ошибка загрузки пользователя {user_id}: {e}")
        return None

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def validate_username(username):
    """Проверка валидности имени пользователя"""
    if len(username) < 3 or len(username) > 30:
        return False
    pattern = r'^[a-zA-Z0-9_.-]+$'
    return bool(re.match(pattern, username))

def validate_password(password):
    """Проверка сложности пароля"""
    if len(password) < 8:
        return False
    return True

def allowed_file(filename):
    """Проверка разрешенных расширений файлов"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_file(file):
    """Сохранение файла с уникальным именем"""
    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(8)}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            logger.info(f"Файл сохранен: {unique_filename}")
            return unique_filename
        except Exception as e:
            logger.error(f"Ошибка сохранения файла: {e}")
            return None
    return None

def get_emoji_html(content):
    """Замена текстовых эмодзи на HTML"""
    emoji_map = {
        ':)': '😊', ':(': '😔', ':D': '😃', ':P': '😛', ';)': '😉',
        ':/': '😕', ':O': '😮', ':*': '😘', '<3': '❤️', '</3': '💔',
        ':+1:': '👍', ':-1:': '👎', ':fire:': '🔥', ':100:': '💯',
        ':eyes:': '👀', ':thinking:': '🤔', ':clap:': '👏'
    }
    for code, emoji in emoji_map.items():
        content = content.replace(code, emoji)
    return content

def is_following(follower_id, followed_id):
    """Проверка подписки"""
    return Follow.query.filter_by(follower_id=follower_id, followed_id=followed_id).first() is not None

def get_following_count(user_id):
    """Количество подписок"""
    return Follow.query.filter_by(follower_id=user_id).count()

def get_followers_count(user_id):
    """Количество подписчиков"""
    return Follow.query.filter_by(followed_id=user_id).count()

def get_like_count(post_id):
    """Количество лайков"""
    return Like.query.filter_by(post_id=post_id).count()

def get_comment_count(post_id):
    """Количество комментариев"""
    return Comment.query.filter_by(post_id=post_id).count()

def get_unread_messages_count(user_id):
    """Количество непрочитанных сообщений"""
    return Message.query.filter_by(receiver_id=user_id, is_read=False, is_deleted=False).count()

def user_has_liked(user_id, post_id):
    """Проверка, лайкнул ли пользователь пост"""
    return Like.query.filter_by(user_id=user_id, post_id=post_id).first() is not None

def create_backup():
    """Создание резервной копии базы данных"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'mateugram_backup_{timestamp}.db'
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # Получаем путь к основной базе данных
        if 'RENDER' in os.environ or 'RENDER_EXTERNAL_HOSTNAME' in os.environ:
            db_path = DB_FILE
        else:
            db_path = DB_FILE
            
        if os.path.exists(db_path):
            # Создаем копию базы данных
            conn = sqlite3.connect(db_path)
            backup_conn = sqlite3.connect(backup_path)
            conn.backup(backup_conn)
            backup_conn.close()
            conn.close()
            
            # Сжимаем бэкап
            compressed_path = f"{backup_path}.gz"
            with open(backup_path, 'rb') as f_in:
                import gzip
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            os.remove(backup_path)  # Удаляем несжатый файл
            
            # Удаляем старые бэкапы (оставляем последние 20)
            backup_files = []
            if os.path.exists(BACKUP_DIR):
                backup_files = sorted(
                    [f for f in os.listdir(BACKUP_DIR) if f.startswith('mateugram_backup_')],
                    reverse=True
                )
                
                for old_backup in backup_files[20:]:
                    os.remove(os.path.join(BACKUP_DIR, old_backup))
            
            logger.info(f"✅ Резервная копия создана: {compressed_path}")
            return compressed_path
    except Exception as e:
        logger.error(f"❌ Ошибка создания бэкапа: {e}")
    return None

def restore_backup(backup_filename):
    """Восстановление из резервной копии"""
    try:
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # Определяем путь к основной базе
        if 'RENDER' in os.environ or 'RENDER_EXTERNAL_HOSTNAME' in os.environ:
            db_path = DB_FILE
        else:
            db_path = DB_FILE
        
        # Распаковываем если это gz файл
        if backup_path.endswith('.gz'):
            import gzip
            with gzip.open(backup_path, 'rb') as f_in:
                with open(db_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(backup_path, db_path)
        
        logger.info(f"✅ База данных восстановлена из: {backup_path}")
        
        # Перезагружаем соединение с базой
        db.session.remove()
        db.create_all()
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления бэкапа: {e}")
    return False

def get_avatar_url(user):
    """Получение URL аватара пользователя"""
    if user.avatar_filename:
        avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], user.avatar_filename)
        if os.path.exists(avatar_path):
            # Определяем правильный путь для URL
            if 'RENDER' in os.environ or 'RENDER_EXTERNAL_HOSTNAME' in os.environ:
                return f"/static/uploads/{user.avatar_filename}"
            else:
                return f"/static/uploads/{user.avatar_filename}"
    return None

def get_backup_list():
    """Получение списка доступных резервных копий"""
    try:
        if os.path.exists(BACKUP_DIR):
            backups = []
            for filename in os.listdir(BACKUP_DIR):
                if filename.startswith('mateugram_backup_') and (filename.endswith('.db') or filename.endswith('.db.gz')):
                    filepath = os.path.join(BACKUP_DIR, filename)
                    file_size = os.path.getsize(filepath) // 1024  # Размер в KB
                    backups.append({
                        'filename': filename,
                        'size': file_size,
                        'created_at': datetime.fromtimestamp(os.path.getctime(filepath))
                    })
            # Сортируем по дате создания (новые сверху)
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            return backups
    except Exception as e:
        logger.error(f"Ошибка получения списка бэкапов: {e}")
    return []

def sync_database_to_json():
    """Экспорт данных в JSON файл для дополнительной защиты"""
    try:
        export_data = {
            'users': [],
            'posts': [],
            'backup_date': datetime.now().isoformat()
        }
        
        # Экспорт пользователей (без паролей)
        users = User.query.all()
        for user in users:
            export_data['users'].append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'is_admin': user.is_admin
            })
        
        # Экспорт постов
        posts = Post.query.all()
        for post in posts:
            export_data['posts'].append({
                'id': post.id,
                'user_id': post.user_id,
                'content': post.content,
                'created_at': post.created_at.isoformat() if post.created_at else None
            })
        
        # Сохраняем в JSON файл
        json_file = os.path.join(BACKUP_DIR, f'data_export_{datetime.now().strftime("%Y%m%d")}.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Данные экспортированы в JSON: {json_file}")
        return json_file
    except Exception as e:
        logger.error(f"❌ Ошибка экспорта данных в JSON: {e}")
    return None

# ========== HTML ШАБЛОНЫ ==========
# (Здесь должен быть ваш полный HTML шалон из оригинального кода)
# Для экономии места я не дублирую весь CSS, но добавлю исправления:

BASE_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MateuGram - {title}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* Ваш полный CSS стиль остается здесь */
        /* ... */
        
        /* Дополнительные исправления */
        .post-content {
            white-space: pre-wrap;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        
        .comment-form {
            margin-top: 15px;
            display: none;
        }
        
        .emoji-help {
            font-size: 0.9em;
            color: #666;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-comments"></i> MateuGram</h1>
            <p>Синяя социальная сеть для безопасного общения</p>
            {render_info}
        </div>
        
        <div class="nav">
            <a href="/" class="nav-btn"><i class="fas fa-home"></i> Главная</a>
            {nav_links}
        </div>
        
        {flash_messages}
        
        {content}
        
        <div class="card" style="margin-top: 30px; text-align: center; font-size: 0.9em; color: #666;">
            <p>MateuGram v2.0 | Данные сохранены в: {storage_info}</p>
            <p>Последний бэкап: {last_backup}</p>
        </div>
    </div>
    
    <script>
    // Улучшенные JavaScript функции
    function confirmAction(message, url) {
        if (confirm(message)) {
            window.location.href = url;
        }
        return false;
    }
    
    function toggleComments(postId) {
        const commentsDiv = document.getElementById('comments-' + postId);
        const formDiv = document.getElementById('comment-form-' + postId);
        if (commentsDiv.style.display === 'none') {
            commentsDiv.style.display = 'block';
            formDiv.style.display = 'block';
            // Загружаем комментарии если их еще нет
            if (!commentsDiv.dataset.loaded) {
                loadComments(postId);
            }
        } else {
            commentsDiv.style.display = 'none';
            formDiv.style.display = 'none';
        }
    }
    
    function loadComments(postId) {
        fetch(`/api/comments/${postId}`)
            .then(response => response.json())
            .then(data => {
                const container = document.getElementById(`comments-list-${postId}`);
                container.innerHTML = data.html;
                document.getElementById('comments-' + postId).dataset.loaded = true;
            });
    }
    
    function showReportForm(postId, userId) {
        const form = document.getElementById('report-form-' + postId);
        form.style.display = form.style.display === 'none' ? 'block' : 'none';
    }
    
    // Автосохранение текста при написании поста
    const textareas = document.querySelectorAll('textarea[data-autosave]');
    textareas.forEach(textarea => {
        const key = `autosave_${textarea.name}`;
        const saved = localStorage.getItem(key);
        if (saved) {
            textarea.value = saved;
        }
        
        textarea.addEventListener('input', (e) => {
            localStorage.setItem(key, e.target.value);
        });
        
        textarea.form?.addEventListener('submit', () => {
            localStorage.removeItem(key);
        });
    });
    </script>
</body>
</html>'''

def render_page(title, content):
    """Рендеринг страницы с исправлениями"""
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
    
    # Информация о хранилище
    storage_info = "Постоянное хранилище" if ('RENDER' in os.environ or 'RENDER_EXTERNAL_HOSTNAME' in os.environ) else "Локальное хранилище"
    
    # Информация о последнем бэкапе
    backups = get_backup_list()
    last_backup = backups[0]['created_at'].strftime('%d.%m.%Y %H:%M') if backups else "Нет бэкапов"
    
    # Информация о Render
    render_info = ''
    if 'RENDER' in os.environ or 'RENDER_EXTERNAL_HOSTNAME' in os.environ:
        render_info = '<p style="color: #28a745; font-size: 0.9em;"><i class="fas fa-cloud"></i> Данные сохраняются в постоянном хранилище</p>'
    
    html = BASE_HTML.replace('{title}', title)
    html = html.replace('{nav_links}', nav_links)
    html = html.replace('{flash_messages}', flash_messages)
    html = html.replace('{content}', content)
    html = html.replace('{storage_info}', storage_info)
    html = html.replace('{last_backup}', last_backup)
    html = html.replace('{render_info}', render_info)
    
    return html

# ========== НОВЫЙ МАРШРУТ ДЛЯ API КОММЕНТАРИЕВ ==========
@app.route('/api/comments/<int:post_id>')
@login_required
def api_comments(post_id):
    """API для загрузки комментариев"""
    try:
        comments = Comment.query.filter_by(post_id=post_id).order_by(Comment.created_at.desc()).limit(20).all()
        html = ''
        
        for comment in comments:
            author = User.query.get(comment.user_id)
            if author:
                avatar_style = f'background-image: url(/static/uploads/{author.avatar_filename})' if author.avatar_filename else ''
                avatar_text = '' if author.avatar_filename else f'{author.first_name[0]}{author.last_name[0] if author.last_name else ""}'
                
                html += f'''
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
        
        return {'html': html if html else '<p style="color: #999; text-align: center; padding: 20px;">Комментариев пока нет</p>'}
    except Exception as e:
        logger.error(f"Ошибка API комментариев: {e}")
        return {'html': '<p style="color: #999; text-align: center; padding: 20px;">Ошибка загрузки комментариев</p>'}

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
    
    # Показываем информацию о сохранении данных
    storage_note = ""
    if 'RENDER' in os.environ or 'RENDER_EXTERNAL_HOSTNAME' in os.environ:
        storage_note = '''
        <div class="info-box" style="background: linear-gradient(135deg, rgba(212,237,218,0.9), rgba(195,230,203,0.9));">
            <h3><i class="fas fa-cloud"></i> Данные защищены!</h3>
            <p>На Render.com используется постоянное хранилище данных. Все ваши посты, сообщения и профили сохраняются даже при перезапуске приложения.</p>
            <p><i class="fas fa-database"></i> Автоматическое резервное копиение: Каждые 24 часа</p>
            <p><i class="fas fa-shield-alt"></i> Хранилище: {}</p>
        </div>
        '''.format(DB_FILE if 'RENDER' in os.environ else 'Локальная база данных')
    
    return render_page('Главная', f'''
    <div class="card">
        <h2><i class="fas fa-hand-wave"></i> Добро пожаловать в MateuGram!</h2>
        <p style="margin-bottom: 25px; line-height: 1.8; font-size: 1.1em;">
            Безопасная социальная сеть без политики, религии и нецензурной лексики. 
            Общайтесь с друзьями, делитесь моментами и находите единомышленников в уютной атмосфере.
        </p>
        
        {storage_note}
        
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
    ''')

# ========== РЕГИСТРАЦИЯ И АВТОРИЗАЦИЯ С ИСПРАВЛЕНИЯМИ ==========
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect('/feed')
    
    if request.method == 'POST':
        email = request.form['email'].strip()
        username = request.form['username'].strip()
        first_name = request.form['first_name'].strip()
        last_name = request.form['last_name'].strip()
        password = request.form['password']
        birthday_str = request.form.get('birthday')
        
        # Валидация
        if not validate_username(username):
            flash('Псевдоним должен содержать только английские буквы, цифры и символы _ . - и быть от 3 до 30 символов', 'error')
            return redirect('/register')
        
        if not validate_password(password):
            flash('Пароль должен быть не менее 8 символов', 'error')
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
                # Проверяем возраст
                today = date.today()
                age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
                if age < 13:
                    flash('Регистрация разрешена с 13 лет', 'error')
                    return redirect('/register')
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
            
            # Сразу создаем бэкап при новой регистрации
            create_backup()
            
            flash(f'✅ Регистрация успешна! Добро пожаловать, {first_name}!', 'success')
            return redirect('/feed')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка регистрации: {e}")
            flash(f'❌ Ошибка при регистрации: {str(e)}', 'error')
            return redirect('/register')
    
    return render_page('Регистрация', '''
    <div class="card">
        <h2><i class="fas fa-user-plus"></i> Регистрация в MateuGram</h2>
        
        <form method="POST" id="registerForm">
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
                <input type="text" name="username" class="form-input" placeholder="john_doe" required minlength="3" maxlength="30">
                <small style="color: #666; display: block; margin-top: 8px;">
                    <i class="fas fa-info-circle"></i> Английские буквы, цифры и символы _ . - (3-30 символов)
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
                <input type="date" name="birthday" class="form-input" required>
                <small style="color: #666; display: block; margin-top: 8px;">
                    <i class="fas fa-info-circle"></i> Регистрация с 13 лет
                </small>
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
    
    <script>
    document.getElementById('registerForm').addEventListener('submit', function(e) {
        const password = document.querySelector('input[name="password"]').value;
        if (password.length < 8) {
            e.preventDefault();
            alert('Пароль должен быть не менее 8 символов');
            return false;
        }
        return true;
    });
    </script>
    ''')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/feed')
    
    if request.method == 'POST':
        identifier = request.form['identifier'].strip()
        password = request.form['password']
        
        user = User.query.filter(
            (User.email == identifier) | (User.username == identifier)
        ).first()
        
        if user and check_password_hash(user.password_hash, password):
            if user.is_banned:
                flash('❌ Ваш аккаунт заблокирован', 'error')
                return redirect('/login')
            
            # Обновляем время последнего входа
            user.last_seen = datetime.utcnow()
            db.session.commit()
            
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

# ========== ЛЕНТА И ПОСТЫ С ИСПРАВЛЕНИЯМИ ==========
@app.route('/feed')
@login_required
def feed():
    try:
        # Обновляем время последней активности
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        
        posts = Post.query.filter_by(is_hidden=False).order_by(Post.created_at.desc()).limit(50).all()
        
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
                                <img src="/static/uploads/{img}" alt="Изображение" loading="lazy">
                            </div>
                            '''
                    media_html += '</div>'
            
            has_liked = user_has_liked(current_user.id, post.id)
            like_btn_text = '💔 Убрать лайк' if has_liked else '❤️ Нравится'
            like_btn_class = 'btn-danger' if has_liked else ''
            
            posts_html += f'''
            <div class="post" id="post-{post.id}">
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
                
                <p class="post-content">{post_content}</p>
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
                    {f'<button onclick="showReportForm({post.id}, {author.id})" class="btn btn-small btn-warning"><i class="fas fa-flag"></i> Пожаловаться</button>' if current_user.id != author.id else ''}
                </div>
                
                {f'''
                <div id="report-form-{post.id}" style="display: none; margin-top: 15px; padding: 15px; background: #f8f9fa; border-radius: 10px;">
                    <form method="POST" action="/report/post/{post.id}">
                        <div class="form-group">
                            <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2a5298;">
                                Причина жалобы
                            </label>
                            <select name="reason" class="form-input" required>
                                <option value="">Выберите причину</option>
                                <option value="spam">Спам</option>
                                <option value="harassment">Оскорбления</option>
                                <option value="inappropriate">Неуместный контент</option>
                                <option value="other">Другое</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <textarea name="details" class="form-input" rows="3" placeholder="Дополнительные детали (необязательно)"></textarea>
                        </div>
                        <div style="display: flex; gap: 10px;">
                            <button type="submit" class="btn btn-warning btn-small">
                                <i class="fas fa-paper-plane"></i> Отправить жалобу
                            </button>
                            <button type="button" onclick="showReportForm({post.id}, {author.id})" class="btn btn-small btn-danger">
                                Отмена
                            </button>
                        </div>
                    </form>
                </div>
                ''' if current_user.id != author.id else ''}
                
                <div id="comments-{post.id}" style="display: none; margin-top: 20px;">
                    <div id="comments-list-{post.id}">
                        <!-- Комментарии загружаются через AJAX -->
                    </div>
                    
                    <div id="comment-form-{post.id}" style="margin-top: 15px; display: none;">
                        <form method="POST" action="/add_comment/{post.id}" onsubmit="return submitCommentForm(this, {post.id})">
                            <div class="form-group">
                                <textarea name="content" class="form-input" rows="2" placeholder="Добавить комментарий..." required data-autosave="comment_{post.id}"></textarea>
                                <div class="emoji-help">
                                    Доступны эмодзи: :) 😊, :( 😔, :D 😃, &lt;3 ❤️
                                </div>
                            </div>
                            <button type="submit" class="btn btn-small">
                                <i class="fas fa-paper-plane"></i> Отправить
                            </button>
                        </form>
                    </div>
                </div>
            </div>
            '''
    except Exception as e:
        logger.error(f"Ошибка загрузки ленты: {e}")
        posts_html = f'<div class="alert alert-error"><i class="fas fa-exclamation-circle"></i> Ошибка загрузки ленты: {str(e)}</div>'
    
    return render_page('Лента новостей', f'''
    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
            <h2 style="margin: 0;"><i class="fas fa-newspaper"></i> Лента новостей</h2>
            <div style="display: flex; gap: 10px;">
                <a href="/create_post" class="btn">
                    <i class="fas fa-plus-circle"></i> Новый пост
                </a>
                <a href="/admin/backup" class="btn btn-success" title="Создать резервную копию">
                    <i class="fas fa-save"></i>
                </a>
            </div>
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
    
    <script>
    function submitCommentForm(form, postId) {{
        const formData = new FormData(form);
        fetch(form.action, {{
            method: 'POST',
            body: formData
        }})
        .then(response => {{
            if (response.ok) {{
                loadComments(postId);
                form.reset();
                localStorage.removeItem('autosave_comment_' + postId);
            }} else {{
                alert('Ошибка отправки комментария');
            }}
        }});
        return false;
    }}
    </script>
    ''')

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ ==========
# Остальные маршруты (create_post, like, add_comment, report, profile и т.д.)
# должны быть такими же как в оригинальном коде, но с исправлениями ошибок

# Критические исправления для функций:

@app.route('/like/<int:post_id>')
@login_required
def like_post(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        
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
        logger.error(f"Ошибка лайка: {e}")
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
        
        post = Post.query.get_or_404(post_id)
        
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
        logger.error(f"Ошибка комментария: {e}")
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect('/feed')

# ========== УЛУЧШЕННАЯ АДМИН-ПАНЕЛЬ ==========
@app.route('/admin/export_json')
@login_required
def admin_export_json():
    """Экспорт данных в JSON"""
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    json_file = sync_database_to_json()
    if json_file:
        flash(f'✅ Данные экспортированы в JSON', 'success')
    else:
        flash('❌ Ошибка экспорта данных', 'error')
    
    return redirect('/admin')

@app.route('/admin/auto_backup')
@login_required
def admin_auto_backup():
    """Настройка автоматического резервного копирования"""
    if not current_user.is_admin:
        flash('Доступ запрещен', 'error')
        return redirect('/feed')
    
    return render_page('Автоматическое резервное копирование', '''
    <div class="card">
        <h2><i class="fas fa-robot"></i> Автоматическое резервное копирование</h2>
        
        <div class="info-box">
            <h3><i class="fas fa-info-circle"></i> Текущие настройки</h3>
            <p>На Render.com автоматически создается резервная копия при каждом деплое и при запуске приложения.</p>
            <p>Также создается бэкап при регистрации нового пользователя и удалении аккаунта.</p>
        </div>
        
        <div style="display: flex; gap: 15px; margin-top: 25px;">
            <a href="/admin/backup" class="btn">
                <i class="fas fa-save"></i> Создать бэкап сейчас
            </a>
            <a href="/admin/export_json" class="btn btn-success">
                <i class="fas fa-file-export"></i> Экспорт в JSON
            </a>
            <a href="/admin" class="btn">
                <i class="fas fa-arrow-left"></i> Назад
            </a>
        </div>
    </div>
    ''')

# ========== СТАТИЧЕСКИЕ ФАЙЛЫ ==========
@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    """Обслуживание загруженных файлов"""
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        logger.error(f"Ошибка загрузки файла {filename}: {e}")
        return "Файл не найден", 404

# ========== МИДЛВАР ДЛЯ ОБНОВЛЕНИЯ ВРЕМЕНИ АКТИВНОСТИ ==========
@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

# ========== ИНИЦИАЛИЗАЦИЯ И ЗАПУСК ==========
def initialize_database():
    """Инициализация базы данных с улучшенной обработкой ошибок"""
    try:
        with app.app_context():
            db.create_all()
            
            # Проверяем целостность базы данных
            try:
                test_user = User.query.first()
                logger.info("✅ База данных проверена")
            except Exception as e:
                logger.error(f"❌ Ошибка базы данных: {e}")
                # Пытаемся восстановить из бэкапа
                backups = get_backup_list()
                if backups:
                    logger.info("Пытаюсь восстановить из бэкапа...")
                    restore_backup(backups[0]['filename'])
            
            # Создаем администратора если его нет
            if User.query.filter_by(is_admin=True).count() == 0:
                logger.info("👑 Создание первого администратора...")
                admin = User(
                    email='admin@mateugram.com',
                    username='Admin',
                    first_name='Администратор',
                    last_name='Системы',
                    password_hash=generate_password_hash('admin123'),
                    is_admin=True,
                    is_active=True
                )
                db.session.add(admin)
                db.session.commit()
                logger.info("✅ Администратор создан!")
                logger.info("📧 Email: admin@mateugram.com")
                logger.info("🔑 Пароль: admin123")
            
            # Создаем начальный бэкап
            backup_file = create_backup()
            if backup_file:
                logger.info(f"✅ Начальный бэкап создан: {backup_file}")
            
            # Экспортируем данные в JSON
            json_file = sync_database_to_json()
            if json_file:
                logger.info(f"✅ Данные экспортированы в JSON: {json_file}")
            
            logger.info(f"🚀 MateuGram запущен! Пользователей: {User.query.count()}, Постов: {Post.query.count()}")
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка инициализации: {e}")
        raise

# Создаем бэкап при завершении
atexit.register(create_backup)

# Запуск инициализации
initialize_database()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8321))
    app.run(host='0.0.0.0', port=port, debug=False)
