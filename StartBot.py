from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from cryptography.fernet import Fernet
import os
import uuid
import shutil
import tempfile
import json
import base64
from typing import Optional

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
KEYS_FILE = os.path.join("user_files", "keys.json")


def load_token():
    try:
        with open('token.txt', 'r', encoding='utf-8') as file:
            return file.read().strip()
    except FileNotFoundError:
        print("ERROR: token.txt file not found!")
        return None


def ensure_user_files_dir():
    os.makedirs("user_files", exist_ok=True)


def _atomic_write_json(path: str, data: dict):
    """Записывает JSON атомарно через временный файл + replace."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_keys_dict() -> dict:
    ensure_user_files_dir()
    if not os.path.exists(KEYS_FILE):
        # создаём пустой словарь ключей
        _atomic_write_json(KEYS_FILE, {})
        return {}
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # в случае повреждения файла — резервная инициализация
        _atomic_write_json(KEYS_FILE, {})
        return {}


def _save_keys_dict(d: dict):
    ensure_user_files_dir()
    _atomic_write_json(KEYS_FILE, d)


def get_user_fernet(user_id: int) -> Fernet:
    """
    Возвращает объект Fernet, привязанный к user_id.
    Ключ хранится в user_files/keys.json в виде base64-строки.
    """
    keys = _load_keys_dict()
    uid = str(user_id)
    if uid in keys:
        try:
            key_b64 = keys[uid]
            key = base64.b64decode(key_b64)
            return Fernet(key)
        except Exception:
            # если ключ повреждён — сгенерируем новый и перезапишем
            pass

    # генерируем новый ключ, сохраняем и возвращаем
    key = Fernet.generate_key()
    keys[uid] = base64.b64encode(key).decode("ascii")
    _save_keys_dict(keys)
    return Fernet(key)


def sanitize_filename(filename: str) -> str:
    """Removes potentially dangerous characters"""
    safe = "".join(c for c in filename if c.isalnum() or c in (' ', '.', '_', '-')).strip()
    return safe or f"file_{uuid.uuid4().hex[:8]}"


TOKEN = load_token()

if TOKEN is None:
    print("Bot cannot start without token!")
    exit()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'PLEASE READ THE PRIVACY POLICY BEFORE USING IT.\n'
        'clck.ru/3Q7HCn'
    )
    await update.message.reply_text(
        "📁 Hello! I am your cloud storage!\n\n"
        "Commands:\n"
        "/getfiles - view my files\n"
        "/getfile <name> - download file\n"
        "/export - export all files\n\n"
        "Or just send me a file or photo to save!\n\n"
        "🔒 All files are encrypted for your security!"
    )


async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves and encrypts user's file"""
    user_id = update.message.from_user.id
    fernet = get_user_fernet(user_id)

    # Получаем file object и имя
    if update.message.document:
        file = await update.message.document.get_file()
        file_name = update.message.document.file_name or f"doc_{uuid.uuid4().hex[:8]}"
        file_size = update.message.document.file_size
    elif update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_name = f"photo_{uuid.uuid4().hex[:8]}.jpg"
        file_size = photo.file_size
    else:
        await update.message.reply_text("❌ File type not supported")
        return

    # Проверка размера по мета-данным (если доступно)
    if file_size and file_size > MAX_FILE_SIZE:
        await update.message.reply_text("❌ File too large (max 50 MB)")
        return

    # Создаём папку пользователя
    user_folder = f"user_files/user_{user_id}"
    os.makedirs(user_folder, exist_ok=True)

    # Сanitize
    safe_name = sanitize_filename(file_name)

    # Временный файл (в папке пользователя)
    fd, temp_path = tempfile.mkstemp(prefix="tmp_", dir=user_folder)
    os.close(fd)  # закроем дескриптор, telegram напишет в файл по пути

    try:
        # Скачиваем во временный файл
        await file.download_to_drive(temp_path)

        # Проверим фактический размер
        if os.path.getsize(temp_path) > MAX_FILE_SIZE:
            os.remove(temp_path)
            await update.message.reply_text("❌ File too large (max 50 MB)")
            return

        # Читаем, шифруем и сохраняем
        with open(temp_path, "rb") as f:
            data = f.read()

        encrypted = fernet.encrypt(data)
        encrypted_path = os.path.join(user_folder, safe_name)
        with open(encrypted_path, "wb") as f:
            f.write(encrypted)

        await update.message.reply_text(f"✅ File '{safe_name}' saved and encrypted!")

    except Exception as e:
        await update.message.reply_text(f"❌ Encryption error: {e}")
    finally:
        # Удаляем временный файл, если остался
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


async def get_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows user's file list"""
    user_id = update.message.from_user.id
    user_folder = f"user_files/user_{user_id}"

    if not os.path.exists(user_folder):
        await update.message.reply_text("📭 You don't have any saved files yet.")
        return

    files = [f for f in os.listdir(user_folder) if f != 'key.key' and not f.startswith("tmp_")]
    if not files:
        await update.message.reply_text("📭 You don't have any saved files yet.")
        return

    file_list = "\n".join([f"📄 {i + 1}. {file}" for i, file in enumerate(files)])
    await update.message.reply_text(f"📂 Your files:\n{file_list}")


async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Decrypts and sends file to user"""
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text("❌ Specify the file name: /getfile file_name")
        return

    requested_raw = " ".join(context.args)
    file_name = sanitize_filename(requested_raw)

    user_folder = f"user_files/user_{user_id}"
    encrypted_file_path = os.path.join(user_folder, file_name)

    if not os.path.exists(encrypted_file_path):
        await update.message.reply_text("❌ File not found")
        return

    fernet = get_user_fernet(user_id)

    # Временный файл для отправки
    fd, temp_path = tempfile.mkstemp(prefix="dec_", dir=user_folder)
    os.close(fd)
    try:
        with open(encrypted_file_path, "rb") as f:
            encrypted_data = f.read()

        decrypted = fernet.decrypt(encrypted_data)

        with open(temp_path, "wb") as f:
            f.write(decrypted)

        # Отправляем
        with open(temp_path, "rb") as f:
            await update.message.reply_document(document=f, filename=file_name)
    except Exception as e:
        await update.message.reply_text(f"❌ Decryption error: {e}")
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


async def export_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exports and decrypts all user files into a ZIP archive"""
    user_id = update.message.from_user.id
    user_folder = f"user_files/user_{user_id}"

    if not os.path.exists(user_folder):
        await update.message.reply_text("📭 You don't have any files to export.")
        return

    fernet = get_user_fernet(user_id)

    # Создадим временную директорию для распаковки
    with tempfile.TemporaryDirectory() as tmpdir:
        exported_count = 0
        files = [f for f in os.listdir(user_folder) if not f.startswith("tmp_") and f != 'key.key']
        for fname in files:
            enc_path = os.path.join(user_folder, fname)
            try:
                with open(enc_path, "rb") as f:
                    enc = f.read()
                dec = fernet.decrypt(enc)
                out_path = os.path.join(tmpdir, fname)
                # Записать расшифрованный файл во временную папку
                with open(out_path, "wb") as out:
                    out.write(dec)
                exported_count += 1
            except Exception as e:
                # Не прерываем весь экспорт из-за одной ошибки
                await update.message.reply_text(f"❌ Error exporting {fname}: {e}")

        if exported_count == 0:
            await update.message.reply_text("❌ No files could be exported (maybe decryption failed).")
            return

        # Создаём архив
        archive_base = os.path.join("exports", f"export_user_{user_id}_{uuid.uuid4().hex[:8]}")
        os.makedirs("exports", exist_ok=True)
        archive_path = shutil.make_archive(archive_base, 'zip', tmpdir)

        # Отправляем архив
        try:
            with open(archive_path, "rb") as a:
                await update.message.reply_document(document=a, filename=os.path.basename(archive_path))
            await update.message.reply_text(f"✅ Export completed: {exported_count}/{len(files)} files.")
        finally:
            # Удаляем архив
            try:
                if os.path.exists(archive_path):
                    os.remove(archive_path)
            except Exception:
                pass


def main():
    ensure_user_files_dir()
    token = load_token()
    if not token:
        print("Token not found. Place token in token.txt")
        return

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getfiles", get_files))
    app.add_handler(CommandHandler("getfile", get_file))
    app.add_handler(CommandHandler("export", export_files))

    app.add_handler(MessageHandler(filters.Document.ALL, save_file))
    app.add_handler(MessageHandler(filters.PHOTO, save_file))

    print("Encrypted cloud storage bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
