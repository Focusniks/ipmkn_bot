import logging
import pathlib
import json
import random
import os
from typing import Any, Coroutine

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import Error
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from datetime import datetime

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы состояний
FULL_NAME, CONFIRM_NAME, TUTOR_CODE_INPUT, TUTOR_AUTH, PHONE_NUMBER, MENU = range(6)
EVENT_REGISTRATION, SKS_PHOTO = range(6, 8)
CHOOSE_GROUP, BROADCAST_MESSAGE = range(10, 12)

# Роли
ROLE_STUDENT = 'student'
ROLE_TUTOR = 'tutor'
ROLE_ADMIN = 'admin'


# Подключение к БД
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME')
        )
        return connection
    except Error as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        connection.close()

        if user:
            # Только если студент — показываем меню
            if user['role'] == ROLE_STUDENT:
                await show_main_menu(update, context)
                return MENU
            else:
                await update.message.reply_text(
                    "Вы уже зарегистрированы как тьютор или админ. Используйте /menu."
                )
                return MENU

    # Если пользователь не найден — запрашиваем ФИО (только для студентов)
    await update.message.reply_text(
        "👋 Приветствуем в нашем студенческом боте!\n\n"
        "Давайте познакомимся — напишите ваше ФИО, чтобы мы могли узнать вас поближе 😊"
    )
    return FULL_NAME

# В обработчике /code — только тьюторы и админы
async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите код авторизации:",
        reply_markup=ReplyKeyboardRemove()
    )
    return TUTOR_CODE_INPUT

# Обработка ввода ФИО
async def handle_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    full_name = update.message.text
    if full_name.isdigit() and len(full_name) == 6:
        return await handle_tutor_auth(update, context)
    context.user_data['full_name'] = full_name

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE full_name = %s",
            (full_name,)
        )
        user = cursor.fetchone()
        cursor.close()
        connection.close()

        if user:
            keyboard = [
                ['✅ Да', '❌ Нет']
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
            await update.message.reply_text(
                f"🔎 Мы нашли похожую запись:\n"
                f"👤 {user['full_name']} (№ зачётки: {user['student_id']})\n\n"
                "Это вы? Подтвердите, пожалуйста 👇",
                reply_markup=reply_markup
            )
            context.user_data['found_user'] = user
            return CONFIRM_NAME

    await update.message.reply_text(
        "😔 Увы, такого ФИО не найдено в базе.\n"
        "Проверьте правильность написания и попробуйте ещё раз!"
    )
    return FULL_NAME


# Подтверждение ФИО
async def confirm_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text
    if choice == '✅ Да':
        user_data = context.user_data['found_user']
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE users SET telegram_id = %s, telegram_username = %s WHERE id = %s",
                (update.effective_user.id, update.effective_user.username, user_data['id'])
            )
            connection.commit()
            cursor.close()
            connection.close()

        await update.message.reply_text(
            "🎉 Отлично! Вы успешно авторизованы.\n"
            "Теперь, пожалуйста, введите ваш номер телефона для связи 📱",
            reply_markup=ReplyKeyboardRemove()
        )
        return PHONE_NUMBER
    else:
        await update.message.reply_text("Введите ваше ФИО ещё раз:")
        return FULL_NAME


# Обработка номера телефона
async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone_number = update.message.text
    context.user_data['phone_number'] = phone_number

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE users SET phone_number = %s WHERE telegram_id = %s",
            (phone_number, update.effective_user.id)
        )
        connection.commit()
        cursor.close()
        connection.close()

    await update.message.reply_text(
        "✅ Ваш номер телефона сохранён!\n"
        "Теперь вы можете пользоваться всеми возможностями бота 🚀"
    )
    return await show_main_menu(update, context)


# Показ главного меню
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    connection = get_db_connection()
    user = None
    tutor_name = "-"  # ← добавьте эту строку

    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        connection.close()

    if not user:
        await update.message.reply_text("❌ Пользователь не найден. Начните с /start")
        return ConversationHandler.END

    if user['role'] == ROLE_STUDENT:
        tutor_name = "-"
        group = user.get('group_name')
        if group:
            connection = get_db_connection()
            if connection:
                cursor1 = connection.cursor(dictionary=True)
                cursor1.execute(
                    "SELECT tutor_id FROM tutor_groups WHERE group_name = %s", (group,)
                )
                tutor_groups = cursor1.fetchall()
                cursor1.close()  # теперь можно безопасно закрыть

                tutor_name = "-"
                if tutor_groups:
                    tutor_group = tutor_groups[0]
                    cursor2 = connection.cursor(dictionary=True)
                    cursor2.execute(
                        "SELECT full_name FROM users WHERE id = %s AND role = 'tutor'", (tutor_group['tutor_id'],)
                    )
                    tutors = cursor2.fetchall()
                    if tutors:
                        tutor_name = tutors[0]['full_name']
                    cursor2.close()
                connection.close()
    menu_text = (
        f"👋 Привет, {user['full_name']}!\n"
        f"📚 Вот ваши данные:\n"
        f"• № зачётки: {user.get('student_id', '-')}\n"
        f"• Группа: {user.get('group_name', '-')}\n"
        f"• Баллы: {user.get('points', 0)}\n"
        f"• Ваш тьютор: {tutor_name}\n\n"
    )

    if user['role'] == ROLE_TUTOR or user['role'] == ROLE_ADMIN:
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
            tutor = cursor.fetchone()
            groups = []
            if tutor:
                cursor.execute("SELECT group_name FROM tutor_groups WHERE tutor_id = %s", (tutor['id'],))
                groups = [row['group_name'] for row in cursor.fetchall()]
            cursor.close()
            connection.close()
            menu_text = (
                f"👋 Привет, {user['full_name']}!\n"
                f"• Тьютор групп(ы): {', '.join(groups) if groups else '-'}\n"
            )

    # Формирование клавиатуры для каждой роли
    if user['role'] == ROLE_STUDENT:
        keyboard = [
            ['📅 Календарь мероприятий', '✅ Отметиться на мероприятии'],
            ['🎫 Зарегистрироваться в СКС', '❓ Помощь']
        ]
    elif user['role'] == ROLE_TUTOR:
        keyboard = [
            ['📅 Календарь мероприятий', '📊 Баллы студентов'],
            ['📢 Рассылка для группы', '📊 Статистика']
        ]
    elif user['role'] == ROLE_ADMIN:
        keyboard = [
            ['📅 Управление мероприятиями', '📊 Изменить баллы'],
            ['📢 Рассылка', '📊 Статистика'],
            ['👥 Управление пользователями']
        ]
    else:
        keyboard = [['❓ Помощь']]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(menu_text, reply_markup=reply_markup)
    return MENU

async def tutor_broadcast_entry(update, context):
    user_id = update.effective_user.id
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s AND role = 'tutor'", (user_id,))
        tutor = cursor.fetchone()
        if tutor:
            cursor.execute("SELECT group_name FROM tutor_groups WHERE tutor_id = %s", (tutor['id'],))
            groups = [row['group_name'] for row in cursor.fetchall()]
            cursor.close()
            connection.close()
            if groups:
                # Если у тьютора одна группа — сразу выбираем её
                context.user_data['broadcast_target'] = groups[0] if len(groups) == 1 else groups
                await update.message.reply_text("📨 Введите сообщение для рассылки группе:")
                return BROADCAST_MESSAGE
            else:
                await update.message.reply_text("❌ У вас нет прикреплённых групп.")
        else:
            await update.message.reply_text("❌ Вы не тьютор.")
    return ConversationHandler.END

# Проверка кода авторизации
async def handle_tutor_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text
    if code == os.getenv('TUTOR_CODE'):
        await update.message.reply_text("Введите ваш персональный 6-значный код:")
        return TUTOR_AUTH
    else:
        await update.message.reply_text("❌ Неверный код. Попробуйте снова через /start")
        return ConversationHandler.END


# Обработка персонального кода тьютора/админа
async def handle_tutor_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    personal_code = update.message.text
    telegram_id = update.effective_user.id
    telegram_username = update.effective_user.username

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tutors WHERE code = %s", (personal_code,))
        tutor = cursor.fetchone()

        if tutor and tutor['user_id']:
            cursor.execute("SELECT * FROM users WHERE id = %s", (tutor['user_id'],))
            user = cursor.fetchone()

            if user:
                if user['telegram_id']:
                    await update.message.reply_text("❌ Этот профиль уже привязан к другому Telegram аккаунту.")
                    cursor.close()
                    connection.close()
                    return ConversationHandler.END

                cursor.execute(
                    "UPDATE users SET telegram_id = %s, telegram_username = %s WHERE id = %s",
                    (telegram_id, telegram_username, user['id'])
                )
                connection.commit()
                cursor.close()
                connection.close()

                await update.message.reply_text("✅ Авторизация успешна! Вы теперь тьютор.")
                await show_main_menu(update, context)
                return ConversationHandler.END
            else:
                cursor.close()
                connection.close()
                await update.message.reply_text("❌ Профиль пользователя не найден. Обратитесь к администратору.")
                return ConversationHandler.END
        else:
            cursor.close()
            connection.close()
            await update.message.reply_text("❌ Код не найден или не привязан к пользователю. Обратитесь к администратору.")
            return ConversationHandler.END

# Обработка меню
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    text = update.message.text
    user_id = update.effective_user.id

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        connection.close()

    if not user:
        await update.message.reply_text("❌ Пользователь не авторизован. Начните с /start")
        return ConversationHandler.END

    if context.user_data.get('user_search'):
        search_term = text
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM users WHERE full_name LIKE %s",
                (f'%{search_term}%',)
            )
            users = cursor.fetchall()
            cursor.close()
            connection.close()

            if users:
                info_text = "🔍 Найденные пользователи:\n\n"
                for u in users:
                    info_text += f"• ID: {u['id']}, ФИО: {u['full_name']}, Группа: {u['group_name']}, Роль: {u['role']}\n"
                await update.message.reply_text(info_text)
            else:
                await update.message.reply_text("❌ Пользователи не найдены.")
        context.user_data['user_search'] = False
        return MENU

    if context.user_data.get('faq_answer_id'):
        question_id = context.user_data['faq_answer_id']
        answer = text
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "UPDATE faq_questions SET answer = %s, status = 'answered' WHERE id = %s",
                (answer, question_id)
            )
            cursor.execute("SELECT user_id FROM faq_questions WHERE id = %s", (question_id,))
            question = cursor.fetchone()
            if question:
                cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = %s", (question['user_id'],))
                user = cursor.fetchone()
                if user and user['telegram_id']:
                    await context.bot.send_message(
                        chat_id=user['telegram_id'],
                        text=f"Ответ на ваш вопрос:\n{answer}"
                    )
                else:
                    logger.warning(
                        f"Не удалось отправить ответ: telegram_id отсутствует для user_id={question['user_id']}")
        connection.commit()
        cursor.close()
        connection.close()
        await update.message.reply_text("✅ Ответ отправлен студенту.")
        context.user_data['faq_answer_id'] = None
        await show_main_menu(update, context)
        return MENU

    if context.user_data.get('ask_question'):
        question = text
        user_id = update.effective_user.id
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO faq_questions (user_id, question) VALUES (%s, %s)",
                (user_id, question)
            )
            question_id = cursor.lastrowid
            connection.commit()
            cursor.close()
            connection.close()
            await update.message.reply_text("✅ Ваш вопрос отправлен тьюторам. Ожидайте ответа.")
            await notify_tutors_about_question(context, question_id, question)
        context.user_data['ask_question'] = False
        return MENU

    if context.user_data.get('add_event_title'):
            event_title = text
            context.user_data['event_title'] = event_title
            await update.message.reply_text(
                "Введите дату мероприятия в формате ДД.ММ.ГГГГ ЧЧ:ММ (например, 15.09.2025 18:00):")
            context.user_data['add_event_date'] = True
            context.user_data['add_event_title'] = False
            return MENU

    if context.user_data.get('add_event_date'):
        event_date_str = text
        from datetime import datetime
        try:
            event_date = datetime.strptime(event_date_str, "%d.%m.%Y %H:%M")
            event_title = context.user_data.get('event_title')
            attendance_code = f"{random.randint(1000, 9999)}"
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO events (title, event_date, attendance_code) VALUES (%s, %s, %s)",
                    (event_title, event_date, attendance_code)
                )
                event_id = cursor.lastrowid
                connection.commit()
                cursor.close()
                connection.close()
                await update.message.reply_text(
                    f"✅ Мероприятие '{event_title}' добавлено на {event_date_str}.\nID: {event_id}\nКод для отметки: {attendance_code}"
                )
            else:
                await update.message.reply_text(
                    "⚠️ Ой! Не удалось подключиться к базе данных.\n"
                    "Попробуйте позже или обратитесь к администратору."
                )
        except ValueError:
            await update.message.reply_text("❌ Некорректный формат даты. Попробуйте ещё раз:")
            return MENU
        context.user_data['add_event_date'] = False
        context.user_data['event_title'] = None
        return await manage_events(update, context)

        # --- Обработка редактирования мероприятия ---
    if context.user_data.get('edit_event'):
        try:
            event_id = int(text)
            context.user_data['edit_event_id'] = event_id
            await update.message.reply_text("Введите новое название мероприятия:")
            context.user_data['edit_event_title'] = True
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID мероприятия.")
        context.user_data['edit_event'] = False
        return MENU

    if context.user_data.get('edit_event_title'):
        new_title = text
        event_id = context.user_data.get('edit_event_id')
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE events SET title = %s WHERE id = %s",
                (new_title, event_id)
            )
            connection.commit()
            cursor.close()
            connection.close()
            await update.message.reply_text(f"✅ Название мероприятия обновлено на '{new_title}'.")
        else:
            await update.message.reply_text(
                "⚠️ Ой! Не удалось подключиться к базе данных.\n"
                "Попробуйте позже или обратитесь к администратору."
            )
        context.user_data['edit_event_title'] = False
        context.user_data['edit_event_id'] = None
        return await manage_events(update, context)

        # --- Обработка удаления мероприятия ---
    if context.user_data.get('delete_event'):
        try:
            event_id = int(text)
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor()
                cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
                connection.commit()
                cursor.close()
                connection.close()
                await update.message.reply_text(f"🗑️ Мероприятие с ID {event_id} удалено.")
            else:
                await update.message.reply_text(
                    "⚠️ Ой! Не удалось подключиться к базе данных.\n"
                    "Попробуйте позже или обратитесь к администратору."
                )
        except ValueError:
            await update.message.reply_text("❌ Введите корректный ID мероприятия.")
        context.user_data['delete_event'] = False
        return await manage_events(update, context)

    if context.user_data.get('attendance_mark'):
        code = text.strip()
        user_id = update.effective_user.id
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id FROM events WHERE attendance_code = %s", (code,))
            event = cursor.fetchone()
            if event:
                event_id = event['id']
                cursor.execute("SELECT * FROM event_attendance WHERE event_id = %s AND user_id = %s",
                               (event_id, user_id))
                already = cursor.fetchone()
                if already:
                    await update.message.reply_text("Вы уже отмечались на этом мероприятии.")
                else:
                    cursor.execute("INSERT INTO event_attendance (event_id, user_id) VALUES (%s, %s)",
                                   (event_id, user_id))
                    cursor.execute("UPDATE users SET points = points + 1 WHERE telegram_id = %s", (user_id,))
                    connection.commit()
                    await update.message.reply_text("✅ Вы успешно отметились!")
            else:
                await update.message.reply_text("❌ Код мероприятия неверный.")
            cursor.close()
            connection.close()
        else:
            await update.message.reply_text(
                "⚠️ Ой! Не удалось подключиться к базе данных.\n"
                "Попробуйте позже или обратитесь к администратору."
            )
        context.user_data['attendance_mark'] = False
        return MENU

    if context.user_data.get('choose_group'):
        group = update.message.text
        if group == 'Всем группам':
            context.user_data['broadcast_target'] = 'all'
        else:
            context.user_data['broadcast_target'] = group
        context.user_data['choose_group'] = False
        await update.message.reply_text("📨 Отправьте сообщение для рассылки выбранной группе:")
        return BROADCAST_MESSAGE

    if context.user_data.get('choose_points_group'):
        group = text
        context.user_data['choose_points_group'] = False
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            # Получаем id тьютора по telegram_id
            cursor.execute("SELECT id FROM users WHERE telegram_id = %s AND role = 'tutor'", (user_id,))
            tutor = cursor.fetchone()
            if tutor:
                tutor_id = tutor['id']
                if group == 'Всем группам':
                    cursor.execute(
                        "SELECT full_name, group_name, points FROM users WHERE group_name IN (SELECT group_name FROM tutor_groups WHERE tutor_id = %s) AND role = 'student' ORDER BY group_name, points DESC",
                        (tutor_id,)
                    )
                students = cursor.fetchall()
                cursor.close()
                connection.close()
                if students:
                    points_text = "📊 Баллы студентов всех ваших групп:\n\n"
                    for student in students:
                        points_text += f"• {student['full_name']} ({student['group_name']}): {student['points']} баллов\n"
                    await update.message.reply_text(points_text)
                else:
                    await update.message.reply_text("В ваших группах пока нет студентов.")
        else:
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor(dictionary=True)
                cursor.execute(
                    "SELECT full_name, points FROM users WHERE group_name = %s AND role = 'student' ORDER BY points DESC",
                    (group,)
                )
                students = cursor.fetchall()
                cursor.close()
                connection.close()
                if students:
                    points_text = f"📊 Баллы студентов группы {group}:\n\n"
                    for student in students:
                        points_text += f"• {student['full_name']}: {student['points']} баллов\n"
                    await update.message.reply_text(points_text)
                else:
                    await update.message.reply_text("В этой группе пока нет студентов.")
        return MENU

    # Обработка кнопок для студентов
    if user['role'] == ROLE_STUDENT:
        if text == '📅 Календарь мероприятий':
            await show_events(update, context)
        elif text == '📊 Мои баллы':
            await show_my_points(update, context)
        elif text == '🎫 Зарегистрироваться в СКС':
            await request_sks_photo(update, context)
        elif text == '❓ Помощь':
            await show_faq(update, context)
        elif text == '✅ Отметиться на мероприятии':
            await update.message.reply_text("Введите 4-значный код мероприятия:")
            context.user_data['attendance_mark'] = True
        elif text == '✍️ Задать свой вопрос':
            await ask_question_entry(update, context)
        elif text == '↩️ Назад':
            await show_main_menu(update, context)

    # Обработка кнопок для тьюторов
    elif user['role'] == ROLE_TUTOR:
        if text == '📅 Календарь мероприятий':
            await show_events(update, context)
        elif text == '📊 Баллы студентов':
            await choose_points_group(update, context)
        elif text == '📢 Рассылка':
            return await choose_broadcast_group(update, context)
        elif text == '📊 Статистика':
            await stats_command(update, context)

    # Обработка кнопок для админов
    elif user['role'] == ROLE_ADMIN:
        if text == '📅 Управление мероприятиями':
            await manage_events(update, context)
        elif text == '📊 Изменить баллы':
            await start_set_points(update, context)
        elif text == '📢 Рассылка':
            await choose_broadcast_group(update, context)
        elif text == '📊 Статистика':
            await stats_command(update, context)
        elif text == '👥 Управление пользователями':
            await manage_users(update, context)
        elif text == '👥 Список пользователей':
            await show_users_list(update, context)
        elif text == '🔍 Поиск пользователя':
            await update.message.reply_text("Введите ФИО или часть для поиска:")
            context.user_data['user_search'] = True
        elif text == '🔄 Изменить роль':
            await update.message.reply_text("Используйте команду /setrole <user_id> <role>")
        elif text == '↩️ Назад':
            await show_main_menu(update, context)
        elif text == '➕ Добавить мероприятие':
            await update.message.reply_text("Введите название нового мероприятия:")
            context.user_data['add_event_title'] = True
        elif text == '✏️ Редактировать мероприятие':
            await update.message.reply_text("Введите ID мероприятия для редактирования:")
            context.user_data['edit_event'] = True
        elif text == '🗑️ Удалить мероприятие':
            await update.message.reply_text("Введите ID мероприятия для удаления:")
            context.user_data['delete_event'] = True

    else:
        await update.message.reply_text(
            "❌ Такой команды нет. Напишите /menu для возврата в главное меню."
        )
    return MENU

async def choose_points_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s AND role = 'tutor'", (user_id,))
        tutor = cursor.fetchone()
        if tutor:
            cursor.execute("SELECT group_name FROM tutor_groups WHERE tutor_id = %s", (tutor['id'],))
            groups = [row['group_name'] for row in cursor.fetchall()]
            cursor.close()
            connection.close()

            if groups:
                keyboard = [[group] for group in groups]
                keyboard.append(['Всем группам'])
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
                await update.message.reply_text("Выберите группу для просмотра баллов:", reply_markup=reply_markup)
                context.user_data['choose_points_group'] = True
            else:
                await update.message.reply_text("❌ У вас нет курируемых групп.")
        else:
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
    return MENU

async def choose_broadcast_group(update, context):
    user_id = update.effective_user.id
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, role FROM users WHERE telegram_id = %s", (user_id,))
        user = cursor.fetchone()
        groups = []
        if user:
            if user['role'] == 'tutor':
                cursor.execute("SELECT group_name FROM tutor_groups WHERE tutor_id = %s", (user['id'],))
                groups = [row['group_name'] for row in cursor.fetchall()]
            elif user['role'] == 'admin':
                cursor.execute("SELECT DISTINCT group_name FROM tutor_groups")
                groups = [row['group_name'] for row in cursor.fetchall()]
            cursor.close()
            connection.close()
            if groups:
                keyboard = [[group] for group in groups]
                keyboard.append(['Всем группам'])
                keyboard.append(['↩️ Назад'])  # ← добавлено
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
                await update.message.reply_text("Выберите группу для рассылки:", reply_markup=reply_markup)
                return CHOOSE_GROUP
            else:
                await update.message.reply_text("❌ Нет доступных групп для рассылки.")
        else:
            await update.message.reply_text("❌ У вас нет прав для рассылки.")
    return ConversationHandler.END

async def group_chosen(update, context):
    group = update.message.text
    if group == 'Всем группам':
        context.user_data['broadcast_target'] = 'all'
        await update.message.reply_text("📨 Введите сообщение для рассылки выбранной группе:")
        return BROADCAST_MESSAGE
    elif group == '↩️ Назад':
        return await show_main_menu(update, context)
    else:
        context.user_data['broadcast_target'] = group
        await update.message.reply_text("📨 Введите сообщение для рассылки выбранной группе:")
        return BROADCAST_MESSAGE

async def send_broadcast(update, context):
    target = context.user_data.get('broadcast_target')
    message = update.message
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        if target == 'all':
            cursor.execute("SELECT telegram_id FROM users WHERE role = 'student'")
        else:
            cursor.execute("SELECT telegram_id FROM users WHERE group_name = %s AND role = 'student'", (target,))
        users = cursor.fetchall()
        cursor.close()
        connection.close()
        success = 0
        for user in users:
            try:
                if message.text:
                    await context.bot.send_message(chat_id=user['telegram_id'], text=message.text)
                elif message.photo:
                    await context.bot.send_photo(chat_id=user['telegram_id'], photo=message.photo[-1].file_id,
                                            caption=message.caption)
                elif message.document:
                    await context.bot.send_document(chat_id=user['telegram_id'], document=message.document.file_id,
                                            caption=message.caption)
                success += 1
            except Exception as e:
                logger.error(f"Ошибка отправки: {e}")
        await update.message.reply_text(f"✅ Отправлено: {success} из {len(users)}")
    else:
        await update.message.reply_text("❌ Ошибка подключения к базе данных.")
    return ConversationHandler.END

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await show_main_menu(update, context)

async def notify_tutors_about_question(context, question_id, question):
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT telegram_id FROM users WHERE role = 'tutor'")
        tutors = cursor.fetchall()
        cursor.close()
        connection.close()
        for tutor in tutors:
            if tutor['telegram_id']:
                keyboard = [
                    [InlineKeyboardButton("Ответить", callback_data=f"faq_answer_{question_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                try:
                    await context.bot.send_message(
                        chat_id=tutor['telegram_id'],
                        text=f"Новый вопрос от студента:\n\n{question}",
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки вопроса тьютору {tutor['telegram_id']}: {e}")

async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, full_name, group_name, role FROM users LIMIT 30")
        users = cursor.fetchall()
        cursor.close()
        connection.close()

        if users:
            text = "👥 Список пользователей:\n\n"
            for u in users:
                text += f"• ID: {u['id']}, ФИО: {u['full_name']}, Группа: {u['group_name']}, Роль: {u['role']}\n"
            await update.message.reply_text(text)
        else:
            await update.message.reply_text("❌ Пользователи не найдены.")

async def show_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    faq = [
        {"question": "Как изменить номер телефона?", "answer": "Напишите команду /start и следуйте инструкциям."},
        {"question": "Как узнать свои баллы?", "answer": "Нажмите кнопку `📊 Мои баллы` в главном меню."},
        {"question": "Кому писать по вопросам мероприятий?", "answer": "Обратитесь к вашему тьютору или администратору."}
    ]
    text = "❓ *База вопросов:*\n\n"
    for item in faq:
        text += f"• *{item['question']}*\n{item['answer']}\n\n"
    keyboard = [
        ['✍️ Задать свой вопрос'],
        ['↩️ Назад']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def ask_question_entry(update, context):
    await update.message.reply_text("Введите ваш вопрос:")
    context.user_data['ask_question'] = True

async def handle_prof_union(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE users SET is_prof_union = TRUE WHERE telegram_id = %s",
            (user_id,)
        )
        connection.commit()
        cursor.close()
        connection.close()

        await update.message.reply_text("✅ Спасибо за регистрацию в профсоюзе!")


async def manage_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['➕ Добавить мероприятие', '✏️ Редактировать мероприятие'],
        ['🗑️ Удалить мероприятие', '↩️ Назад']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("📅 Управление мероприятиями:", reply_markup=reply_markup)


async def start_set_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Для изменения баллов используйте команду /setpoints <ID_пользователя> <количество_баллов>\n\n"
        "Например: /setpoints 15 10"
    )


async def manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['👥 Список пользователей', '🔍 Поиск пользователя'],
        ['🔄 Изменить роль', '↩️ Назад']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("👥 Управление пользователями:", reply_markup=reply_markup)


# Показ мероприятий
async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM events WHERE event_date >= NOW() ORDER BY event_date LIMIT 10")
        events = cursor.fetchall()
        cursor.close()
        connection.close()

        if events:
            events_text = "📅 Вот список ближайших мероприятий! \n Не пропустите интересные события и получайте баллы за участие 🏆"
            for event in events:
                events_text += f"• {event['title']} - {event['event_date'].strftime('%d.%m.%Y %H:%M')}\n"

            await update.message.reply_text(events_text)
        else:
            await update.message.reply_text("На данный момент мероприятий нет.")


# Показ баллов пользователя
async def show_my_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT points FROM users WHERE telegram_id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        connection.close()

        if user:
            await update.message.reply_text(f"📊 Ваши баллы: {user['points']}")


# Запрос фото для СКС
async def request_sks_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    app_url = "https://drive.google.com/drive/mobile/folders/1zSp_NnUhkJ3ErI19P1bvZLP5naTBjmNh?usp=drive_link"
    await update.message.reply_text(
        f"📲 Скачайте приложение по ссылке:\nДля андроида: {app_url}\n"
        f"Для IOS: https://apps.apple.com/ru/app/скс-рф/id1473711942\n\n"
        "После установки пройдите быструю регистрацию и отправьте скриншот профиля СКС вашему тьютору.\n"
        "Важно, чтобы на скриншоте было видно ваш профиль, а аватарка должна быть вашей настоящей фотографией, с лицом."
    )
    return SKS_PHOTO


# Обработка фото для СКС
async def handle_sks_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1] if update.message.photo else None
    if not photo:
        await update.message.reply_text("❌ Пожалуйста, отправьте фото.")
        return SKS_PHOTO

    user_id = update.effective_user.id
    connection = get_db_connection()
    if not connection:
        await update.message.reply_text(
            "⚠️ Не удалось подключиться к базе данных. Попробуйте позже."
        )
        return SKS_PHOTO

    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO sks_applications (user_id, photo_url, status) VALUES (%s, %s, 'pending')",
            (user_id, photo.file_id)
        )
        connection.commit()
        cursor.close()
        connection.close()
    except Exception as e:
        logger.error(f"Ошибка записи заявки СКС: {e}")
        await update.message.reply_text("❌ Не удалось сохранить заявку. Попробуйте позже.")
        return SKS_PHOTO

    try:
        await notify_admins_about_sks(update, context, user_id, photo.file_id)
    except Exception as e:
        logger.error(f"Ошибка уведомления админов: {e}")

    await update.message.reply_text("✅ Заявка отправлена на рассмотрение!")
    return await show_main_menu(update, context)


# Уведомление админов о новой заявке СКС
async def notify_admins_about_sks(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, photo_id: str):
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE role = 'admin'")
        admins = cursor.fetchall()
        cursor.close()
        sent = 0
        for admin in admins:
            if admin['telegram_id']:
                keyboard = [
                    [InlineKeyboardButton("✅ Одобрить", callback_data=f"sks_approve_{user_id}"),
                     InlineKeyboardButton("❌ Отклонить", callback_data=f"sks_reject_{user_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                try:
                    await context.bot.send_photo(
                        chat_id=admin['telegram_id'],
                        photo=photo_id,
                        caption="Новая заявка на подтверждение в СКС",
                        reply_markup=reply_markup
                    )
                    sent += 1
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления админу: {e}")
        connection.close()
        if sent == 0:
            await update.message.reply_text("❌ Не удалось отправить заявку ни одному админу. Проверьте настройки.")


# Обработка отмены
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# Команда для статистики
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT role FROM users WHERE telegram_id = %s", (user_id,))
        user = cursor.fetchone()

        if user and user['role'] in [ROLE_TUTOR, ROLE_ADMIN]:
            # Получаем статистику по профсоюзу и СКС
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as prof FROM users WHERE is_prof_union = TRUE")
            prof_users = cursor.fetchone()['prof']

            cursor.execute("SELECT COUNT(*) as sks FROM users WHERE is_sks = TRUE")
            sks_users = cursor.fetchone()['sks']

            prof_percentage = (prof_users / total_users * 100) if total_users > 0 else 0
            sks_percentage = (sks_users / total_users * 100) if total_users > 0 else 0

            stats_text = (
                f"📊 Статистика:\n"
                f"• Всего пользователей: {total_users}\n"
                f"• В профсоюзе: {prof_users} ({prof_percentage:.1f}%)\n"
                f"• В СКС: {sks_users} ({sks_percentage:.1f}%)"
            )

            await update.message.reply_text(stats_text)
        else:
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")

        cursor.close()
        connection.close()


# Команда для изменения баллов
async def set_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT role FROM users WHERE telegram_id = %s", (user_id,))
        user = cursor.fetchone()

        if user and user['role'] == ROLE_ADMIN:
            if len(context.args) < 2:
                await update.message.reply_text("❌ Использование: /setpoints <user_id> <points>")
                return

            try:
                target_user_id = int(context.args[0])
                points = int(context.args[1])

                cursor.execute(
                    "UPDATE users SET points = points + %s WHERE id = %s",
                    (points, target_user_id)
                )
                connection.commit()

                await update.message.reply_text(f"✅ Баллы пользователя {target_user_id} изменены на {points}")
            except ValueError:
                await update.message.reply_text("❌ Неверный формат аргументов")
        else:
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")

        cursor.close()
        connection.close()


# Команда для получения информации о пользователе
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT role FROM users WHERE telegram_id = %s", (user_id,))
        user = cursor.fetchone()

        if user and user['role'] == ROLE_ADMIN:
            if not context.args:
                await update.message.reply_text("❌ Использование: /info <ФИО или часть>")
                return

            search_term = ' '.join(context.args)
            cursor.execute(
                "SELECT * FROM users WHERE full_name LIKE %s",
                (f'%{search_term}%',)
            )
            users = cursor.fetchall()

            if users:
                info_text = "🔍 Найденные пользователи:\n\n"
                for u in users:
                    info_text += f"• ID: {u['id']}, ФИО: {u['full_name']}, Группа: {u['group_name']}, Роль: {u['role']}\n"

                await update.message.reply_text(info_text)
            else:
                await update.message.reply_text("❌ Пользователи не найдены.")
        else:
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")

        cursor.close()
        connection.close()


# Обработчик инлайн-кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith('faq_answer_'):
        question_id = int(query.data.split('_')[2])
        tutor_id = query.from_user.id
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT status FROM faq_questions WHERE id = %s", (question_id,))
            question = cursor.fetchone()
            if question and question['status'] == 'pending':
                cursor.execute(
                    "UPDATE faq_questions SET status = 'in_progress', tutor_id = %s WHERE id = %s",
                    (tutor_id, question_id)
                )
                connection.commit()
                await query.edit_message_text("Вы взяли вопрос. Напишите ответ студенту.")
                context.user_data['faq_answer_id'] = question_id
            else:
                await query.edit_message_text("Вопрос уже взят другим тьютором.")
            cursor.close()
            connection.close()

    if query.data.startswith('sks_'):
        action, user_id = query.data.split('_')[1], query.data.split('_')[2]

        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()

            if action == 'approve':
                cursor.execute(
                    "UPDATE users SET is_sks = TRUE WHERE id = %s",
                    (user_id,)
                )
                cursor.execute(
                    "UPDATE sks_applications SET status = 'approved' WHERE user_id = %s AND status = 'pending'",
                    (user_id,)
                )
                await query.edit_message_caption(caption="✅ Заявка одобрена")

                # Уведомляем пользователя
                cursor.execute("SELECT telegram_id FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                if user and user[0]:
                    try:
                        await context.bot.send_message(chat_id=user[0],
                                                       text="✅ Ваша заявка на подтверждение СКС. Спасибо!")
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления пользователю: {e}")

            elif action == 'reject':
                cursor.execute(
                    "UPDATE sks_applications SET status = 'rejected' WHERE user_id = %s AND status = 'pending'",
                    (user_id,)
                )
                await query.edit_message_caption(caption="❌ Заявка отклонена")

                # Уведомляем пользователя
                cursor.execute("SELECT telegram_id FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                if user and user[0]:
                    try:
                        await context.bot.send_message(
                            chat_id=user[0],
                            text="❌ Ваша заявка на подтверждение в СКС отклонена. Пожалуйста, подайте заявку снова."
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления пользователю: {e}")

            connection.commit()
            cursor.close()
            connection.close()


def main() -> None:
    try:
        application = (
            Application.builder()
            .token(os.getenv('BOT_TOKEN'))
            .read_timeout(30)
            .write_timeout(30)
            .build()
        )

        broadcast_conv = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^📢 Рассылка для группы$"), tutor_broadcast_entry),
                MessageHandler(filters.Regex("^📢 Рассылка$"), choose_broadcast_group)
            ],
            states={
                CHOOSE_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, group_chosen)],
                BROADCAST_MESSAGE: [MessageHandler(filters.ALL, send_broadcast)]
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_full_name)],
                CONFIRM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_name)],
                PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number)],
                TUTOR_CODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tutor_code)],
                TUTOR_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tutor_auth)],
                SKS_PHOTO: [MessageHandler(filters.PHOTO, handle_sks_photo)],
                MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu)],
                BROADCAST_MESSAGE: [MessageHandler(filters.ALL, send_broadcast)]  # ← исправлено
            },
            fallbacks=[CommandHandler('cancel', cancel)]
        )

        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("code", code_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("setpoints", set_points_command))
        application.add_handler(CommandHandler("info", info_command))
        application.add_handler(broadcast_conv)
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        print(f"Ошибка запуска бота: {e}")

if __name__ == '__main__':
    main()