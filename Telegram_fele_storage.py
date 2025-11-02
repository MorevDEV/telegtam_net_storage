from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
import uuid
import shutil

TOKEN = '8362749241:AAFgSjPWiCTMre-CZ_mzYVa_D2JWSTfonRU'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📁 Привет! Я твое облачное хранилище!\n\n"
        "Команды:\n"
        "/getfiles - посмотреть мои файлы\n"
        "/getfile <имя> - скачать файл\n"
        "/export - экспортировать все файлы\n\n"
        "Или просто отправь мне файл или фото для сохранения!"
    )

async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет файл от пользователя"""
    user_id = update.message.from_user.id
    
    if update.message.document:
        # Если пользователь отправил документ
        file = await update.message.document.get_file()  # ИСПРАВЛЕНО: убрал reply_
        file_name = update.message.document.file_name
    
    elif update.message.photo:
        # Если пользователь отправил фото
        file = await update.message.photo[-1].get_file()
        file_name = f"photo_{uuid.uuid4().hex[:8]}.jpg"
    else:
        await update.message.reply_text("❌ Файл не поддерживается")
        return

    # Создаем папку для пользователя
    user_folder = f"user_files/user_{user_id}"  # ИСПРАВЛЕНО: добавил _ после user
    if not os.path.exists(user_folder):  # ИСПРАВЛЕНО: правильная проверка существования папки
        os.makedirs(user_folder)
    
    # Сохраняем файл
    file_path = os.path.join(user_folder, file_name)
    await file.download_to_drive(file_path)  # ДОБАВЛЕНО: скачивание файла
    
    await update.message.reply_text(f"✅ Файл '{file_name}' успешно сохранен!")

async def get_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список файлов пользователя"""
    user_id = update.message.from_user.id
    user_folder = f"user_files/user_{user_id}"
    
    if not os.path.exists(user_folder):
        await update.message.reply_text("📭 У вас пока нет сохраненных файлов.")
        return
    
    files = os.listdir(user_folder)
    if not files:
        await update.message.reply_text("📭 У вас пока нет сохраненных файлов.")
        return
    
    file_list = "\n".join([f"📄 {i+1}. {file}" for i, file in enumerate(files)])
    await update.message.reply_text(f"📂 Ваши файлы:\n{file_list}")

async def get_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет конкретный файл пользователю"""
    user_id = update.message.from_user.id
    
    if not context.args:
        await update.message.reply_text("❌ Укажите имя файла: /getfile имя_файла")
        return
    
    file_name = " ".join(context.args)
    user_folder = f"user_files/user_{user_id}"
    file_path = os.path.join(user_folder, file_name)
    
    if not os.path.exists(file_path):
        await update.message.reply_text("❌ Файл не найден!")
        return
    
    # Отправляем файл обратно пользователю
    await update.message.reply_document(
        document=open(file_path, 'rb'),
        filename=file_name
    )

async def export_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспортирует все файлы пользователя в отдельную локальную папку"""
    user_id = update.message.from_user.id
    user_folder = f"user_files/user_{user_id}"
    export_folder = f"export_user_{user_id}"
    
    if not os.path.exists(user_folder):
        await update.message.reply_text("📭 У вас нет файлов для экспорта.")
        return
    
    # Создаем папку для экспорта
    if not os.path.exists(export_folder):
        os.makedirs(export_folder)
    
    # Копируем все файлы
    files = os.listdir(user_folder)
    for file_name in files:
        src_path = os.path.join(user_folder, file_name)
        dst_path = os.path.join(export_folder, file_name)
        shutil.copy2(src_path, dst_path)
    
    await update.message.reply_text(
        f"✅ Все ваши файлы экспортированы в папку:\n"
        f"`{export_folder}`\n\n"
        f"📊 Экспортировано файлов: {len(files)}",
        parse_mode='Markdown'
    )

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getfiles", get_files))
    app.add_handler(CommandHandler("getfile", get_file))
    app.add_handler(CommandHandler("export", export_files))
    
    # Обработчики сообщений с файлами - ДОБАВЛЕНО!
    app.add_handler(MessageHandler(filters.Document.ALL, save_file))
    app.add_handler(MessageHandler(filters.PHOTO, save_file))
    
    print("Бот-хранилище запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()