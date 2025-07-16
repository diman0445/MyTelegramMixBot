import logging
from datetime import datetime, timezone
import pytz # <-- ДОБАВЛЕННЫЙ ИМПОРТ pytz
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
)
import uuid # Импортируем модуль uuid для генерации уникальных ID

# --- ДОБАВЛЕНЫ ИМПОРТЫ ДЛЯ FLASK И THREADING ---
from flask import Flask
from threading import Thread
# --- КОНЕЦ ДОБАВЛЕННЫХ ИМПОРТОВ ---

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    # filename='bot.log' # Эту строку лучше УБРАТЬ для Replit, так как он не будет постоянно писать в файл
)
logger = logging.getLogger(__name__)

# Конфигурация бота
TOKEN = "8191425731:AAHBmgRcOMVTPXzm5_hlATni7pKsLOqCyyM"  # ВАШ ТОКЕН БОТА!
# ID чатов
GROUP_CHAT_ID = -1002816139814  # Общий рабочий чат
ADMIN_IDS = [289350415, 5920291113]  # ID администраторов
ADMIN_USERNAMES = ["@dmi9630", "@MaximZabara"]  # Для упоминаний

# Сотрудники
EMPLOYEES = ["Илья", "Игорь", "Валерий", "Другой"]

# Лимиты и настройки
MAX_INGREDIENTS = 20  # Макс. ингредиентов в замесе
MAX_PHOTOS_PER_INGREDIENT = 5  # Макс. фото на 1 ингредиент
REJECT_REASONS = ["Просрочка", "Плохое качество фото", "Несоответствие рецептуре", "Другое"]

# Состояния для пользователя, создающего замес
(
    AWAIT_RESPONSIBLE,
    AWAIT_PRODUCT_NAME,
    AWAIT_RECIPE,
    AWAIT_INGREDIENT,
    CONFIRMATION
) = range(5)

# Новые состояния для администратора при отклонении
(
    AWAIT_CUSTOM_REJECTION_REASON # Ожидание своей причины отклонения
) = range(5, 6) # Начинаем нумерацию с 5, чтобы не пересекаться с предыдущими

current_mix = {}

def msk_time():
    # Использование pytz для установки часового пояса "Europe/Moscow"
    return datetime.now(timezone.utc).astimezone(pytz.timezone('Europe/Moscow')).strftime("%d.%m.%Y %H:%M")

def get_employees_keyboard():
    return ReplyKeyboardMarkup(
        [[name] for name in EMPLOYEES],
        one_time_keyboard=True,
        resize_keyboard=True
    )

def get_ingredient_keyboard():
    return ReplyKeyboardMarkup(
        [["Добавить фото", "Следующий ингредиент"], ["Завершить"]],
        one_time_keyboard=True,
        resize_keyboard=True
    )

# Функция для создания клавиатуры утверждения/отклонения
# Теперь принимает mix_id для включения в callback_data
def get_approval_keyboard(mix_id: str):
    buttons = [[InlineKeyboardButton("Утвердить", callback_data=f"approve_{mix_id}")]]
    # Добавляем "Своя причина" как отдельную кнопку
    buttons.extend([[InlineKeyboardButton(reason, callback_data=f"reject_{i}_{mix_id}")] for i, reason in enumerate(REJECT_REASONS)])
    buttons.append([InlineKeyboardButton("✏️ Своя причина", callback_data=f"reject_custom_{mix_id}")])
    return InlineKeyboardMarkup(buttons)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_mix.clear()
    await update.message.reply_text(
        "🏭 Начинаем новый замес\nВыберите ответственного сотрудника:",
        reply_markup=get_employees_keyboard()
    )
    return AWAIT_RESPONSIBLE

async def handle_responsible(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text not in EMPLOYEES:
        await update.message.reply_text(
            "❌ Пожалуйста, выберите сотрудника из списка!",
            reply_markup=get_employees_keyboard()
        )
        return AWAIT_RESPONSIBLE

    current_mix.update({
        'responsible': update.message.text,
        'creator_id': update.effective_user.id,
        'timestamp': msk_time()
    })

    await update.message.reply_text(
        "✏️ Введите название готового продукта:"
    )
    return AWAIT_PRODUCT_NAME

async def handle_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.strip():
        await update.message.reply_text(
            "❌ Название продукта обязательно. Пожалуйста, введите название:"
        )
        return AWAIT_PRODUCT_NAME

    current_mix['product_name'] = update.message.text

    await update.message.reply_text(
        "📸 Пришлите фото рецептуры\nУбедитесь, что весь текст читаем!",
        reply_markup=ReplyKeyboardMarkup([["Отменить"]], resize_keyboard=True)
    )
    return AWAIT_RECIPE

async def handle_recipe_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_mix['recipe_photo'] = update.message.photo[-1].file_id

    current_mix['current_ingredient'] = {
        'number': 1,
        'photos': []
    }

    await update.message.reply_text(
        f"🧂 Ингредиент 1\n"
        "Прикрепите первое фото упаковки. На фото должно быть четко видно:\n"
        "• Название продукта\n• Производителя\n• Номер партии\n• Срок годности\n\n"
        f"Можно добавить до {MAX_PHOTOS_PER_INGREDIENT} фото для одного ингредиента!",
        reply_markup=ReplyKeyboardMarkup([["Отменить"]], resize_keyboard=True)
    )
    return AWAIT_INGREDIENT

async def handle_ingredient_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ing = current_mix['current_ingredient']
    if len(ing['photos']) >= MAX_PHOTOS_PER_INGREDIENT:
        await update.message.reply_text(
            f"⚠️ Максимум {MAX_PHOTOS_PER_INGREDIENT} фото на ингредиент!",
            reply_markup=get_ingredient_keyboard()
        )
        return AWAIT_INGREDIENT

    ing['photos'].append(update.message.photo[-1].file_id)

    await update.message.reply_text(
        f"✅ Фото {len(ing['photos'])} для ингредиента {ing['number']} сохранено!\n"
        "Что делаем дальше?",
        reply_markup=get_ingredient_keyboard()
    )
    return AWAIT_INGREDIENT

async def handle_ingredient_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    ing = current_mix['current_ingredient']

    if action == "Отменить":
        await cancel(update, context)
        return ConversationHandler.END

    if action == "Добавить фото":
        if len(ing['photos']) >= MAX_PHOTOS_PER_INGREDIENT:
            await update.message.reply_text(
                f"⚠️ Достигнут лимит фото ({MAX_PHOTOS_PER_INGREDIENT}) для этого ингредиента!",
                reply_markup=get_ingredient_keyboard()
            )
            return AWAIT_INGREDIENT

        await update.message.reply_text(
            f"Отправьте дополнительное фото для ингредиента {ing['number']}",
            reply_markup=ReplyKeyboardMarkup([["Отменить"]], resize_keyboard=True)
        )
        return AWAIT_INGREDIENT

    elif action == "Следующий ингредиент":
        if 'ingredients' not in current_mix:
            current_mix['ingredients'] = []

        current_mix['ingredients'].append(ing)

        if len(current_mix['ingredients']) >= MAX_INGREDIENTS:
            await update.message.reply_text("⚠️ Достигнут лимит ингредиентов!")
            return await finish_ingredients(update, context)

        next_num = ing['number'] + 1
        current_mix['current_ingredient'] = {
            'number': next_num,
            'photos': []
        }

        await update.message.reply_text(
            f"🧂 Ингредиент {next_num}\n"
            "Прикрепите первое фото упаковки:",
            reply_markup=ReplyKeyboardMarkup([["Отменить"]], resize_keyboard=True)
        )
        return AWAIT_INGREDIENT

    elif action == "Завершить":
        if 'ingredients' not in current_mix:
            current_mix['ingredients'] = []

        current_mix['ingredients'].append(ing)
        return await finish_ingredients(update, context)

async def finish_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = len(current_mix['ingredients'])
    photos = sum(len(i['photos']) for i in current_mix['ingredients'])

    await update.message.reply_text(
        f"📋 Итоговая сводка\n"
        f"• Продукт: {current_mix['product_name']}\n"
        f"• Ответственный: {current_mix['responsible']}\n"
        f"• Ингредиентов: {total}\n"
        f"• Всего фото: {photos}\n"
        f"• Время: {current_mix['timestamp']}\n\n"
        "Отправить на проверку администратору?",
        reply_markup=ReplyKeyboardMarkup(
            [["На проверку", "Отменить"]],
            resize_keyboard=True
        )
    )
    return CONFIRMATION

async def send_for_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Генерируем уникальный ID для этого замеса
    mix_id = str(uuid.uuid4())

    # Сохраняем данные замеса в bot_data по этому ID
    # Инициализируем 'pending_mixes' если его нет
    if 'pending_mixes' not in context.bot_data:
        context.bot_data['pending_mixes'] = {}
    context.bot_data['pending_mixes'][mix_id] = current_mix.copy()

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🔔 Новый замес на проверку\n"
                     f"Продукт: {current_mix['product_name']}\n"
                     f"Ответственный: {current_mix['responsible']}\n"
                     f"Ингредиентов: {len(current_mix['ingredients'])}\n"
                     f"Время: {current_mix['timestamp']}",
                reply_markup=get_approval_keyboard(mix_id) # Передаем mix_id в клавиатуру
            )
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=current_mix['recipe_photo'],
                caption="📋 Рецептура"
            )
            for ing in current_mix['ingredients']:
                for i, photo in enumerate(ing['photos'], 1):
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=photo,
                        caption=f"🧂 Ингредиент {ing['number']} (фото {i})"
                    )
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")

    await update.message.reply_text(
        f"✅ Ваш замес отправлен на согласование администраторам: {', '.join(ADMIN_USERNAMES)}",
    )
    current_mix.clear()
    return ConversationHandler.END

async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Извлекаем mix_id из callback_data
    callback_parts = query.data.split('_')
    action_type = callback_parts[0] # "approve" или "reject"
    mix_id = callback_parts[-1] # Последняя часть - это mix_id

    # Получаем данные замеса из bot_data
    mix_data = context.bot_data.get('pending_mixes', {}).get(mix_id, None)

    if not mix_data:
        logger.warning(f"Данные замеса с ID {mix_id} не найдены или уже обработаны.")
        await query.edit_message_text("⚠️ Ошибка: Данные замеса не найдены или уже обработаны.")
        return

    admin_name = query.from_user.first_name
    creator_id = mix_data.get('creator_id')

    if action_type == "approve":
        # Удаляем замес из pending_mixes после утверждения
        context.bot_data['pending_mixes'].pop(mix_id, None)

        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"🟢 Утвержден замес\n"
                     f"Продукт: {mix_data.get('product_name', 'Не указано')}\n"
                     f"Ответственный: {mix_data.get('responsible', 'Не указано')}\n"
                     f"Ингредиентов: {len(mix_data.get('ingredients', []))}\n"
                     f"Время: {mix_data.get('timestamp', 'Не указано')}\n"
                     f"Проверяющий: {admin_name}",
            )
            await context.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=mix_data.get('recipe_photo'),
                caption="📋 Рецептура"
            )
            for ing in mix_data.get('ingredients', []):
                for i, photo in enumerate(ing['photos'], 1):
                    await context.bot.send_photo(
                        chat_id=GROUP_CHAT_ID,
                        photo=photo,
                        caption=f"🧂 Ингредиент {ing['number']} (фото {i})"
                    )
        except Exception as e:
            logger.error(f"Ошибка отправки в групповой чат: {e}")

        if creator_id:
            try:
                await context.bot.send_message(
                    chat_id=creator_id,
                    text=f"✅ Ваш замес утвержден!\n"
                         f"Проверяющий: {admin_name}\n\n"
                         f"Для нового замеса нажмите /start",
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления создателю {creator_id} об утверждении: {e}")
        else:
            logger.warning("creator_id не найден в mix_data при утверждении (после извлечения из bot_data).")

        await query.edit_message_text(f"✅ Замес утвержден ({admin_name})")
        # Завершаем диалог администратора, если он был начат для ввода причины
        return ConversationHandler.END # Важно для завершения конверсации админа

    elif action_type == "reject":
        reason_detail = ""
        if callback_parts[1] == "custom":
            # Если админ выбрал "Своя причина"
            # Сохраняем mix_id и chat_id админа в user_data, чтобы потом получить причину
            context.user_data['pending_custom_rejection'] = {
                'mix_id': mix_id,
                'admin_chat_id': query.message.chat_id,
                'message_to_edit_id': query.message.message_id # Сохраняем ID сообщения для редактирования
            }
            await query.edit_message_text("✏️ Введите свою причину отклонения:")
            return AWAIT_CUSTOM_REJECTION_REASON # Переходим в новое состояние для админа
        else:
            # Если админ выбрал причину из списка
            reason_idx = int(callback_parts[1])
            reason_detail = REJECT_REASONS[reason_idx]
            await _send_rejection_notification(mix_id, reason_detail, admin_name, query, context)
            return ConversationHandler.END # Завершаем диалог администратора

# Новая функция для отправки уведомлений об отклонении (чтобы не дублировать код)
async def _send_rejection_notification(mix_id, reason_detail, admin_name, query_obj, context):
    mix_data = context.bot_data.get('pending_mixes', {}).pop(mix_id, None) # Удаляем замес из pending_mixes
    if not mix_data:
        logger.warning(f"Данные замеса с ID {mix_id} не найдены для отправки уведомления об отклонении.")
        await query_obj.edit_message_text("⚠️ Ошибка: Данные замеса не найдены или уже обработаны.")
        return

    creator_id = mix_data.get('creator_id')

    if creator_id:
        try:
            # Подсвечиваем причину жирным шрифтом
            await context.bot.send_message(
                chat_id=creator_id,
                text=f"❌ Ваш замес отклонен\n"
                     f"Причина: **{reason_detail}**\n" # Причина жирным
                     f"Проверяющий: {admin_name}\n\n"
                     f"Для создания нового замеса нажмите /start",
                parse_mode='Markdown' # Указываем, что используем Markdown
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления создателю {creator_id} об отклонении: {e}")
    else:
        logger.warning("creator_id не найден в mix_data при отклонении (после извлечения из bot_data в _send_rejection_notification).")

    await query_obj.edit_message_text(f"❌ Замес отклонен: {reason_detail} ({admin_name})")

# Новый обработчик для получения своей причины от администратора
async def handle_custom_rejection_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    custom_reason = update.message.text.strip()
    if not custom_reason:
        await update.message.reply_text("Пожалуйста, введите причину или нажмите /cancel для отмены.")
        return AWAIT_CUSTOM_REJECTION_REASON # Остаемся в этом состоянии, пока не получим текст

    pending_data = context.user_data.get('pending_custom_rejection')
    if not pending_data:
        logger.error(f"pending_custom_rejection данные не найдены для админа {update.effective_user.id}")
        await update.message.reply_text("Произошла ошибка при обработке пользовательской причины. Попробуйте снова или нажмите /cancel.")
        return ConversationHandler.END

    mix_id = pending_data['mix_id']
    admin_name = update.effective_user.first_name
    admin_chat_id = pending_data['admin_chat_id']
    message_to_edit_id = pending_data['message_to_edit_id']

    # Отправляем уведомление с пользовательской причиной
    # Используем edit_message_text для изменения исходного сообщения админа
    await _send_rejection_notification(mix_id, custom_reason, admin_name, 
                                       type('obj', (object,), {'edit_message_text': lambda text: context.bot.edit_message_text(chat_id=admin_chat_id, message_id=message_to_edit_id, text=text, parse_mode='Markdown')})(), # Эмулируем query_obj для edit_message_text
                                       context)

    del context.user_data['pending_custom_rejection'] # Очищаем данные админа
    await update.message.reply_text("Причина отклонения отправлена создателю.")
    return ConversationHandler.END # Завершаем диалог администратора

# --- Важно: определение функции cancel ПЕРЕД main() ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли активная конверсация для админа по вводу причины
    if 'pending_custom_rejection' in context.user_data and update.effective_user.id == context.user_data['pending_custom_rejection']['admin_chat_id']:
        del context.user_data['pending_custom_rejection']
        await update.message.reply_text("Отмена ввода причины. Вы вышли из режима ввода пользовательской причины.", reply_markup=ReplyKeyboardRemove())
    else:
        current_mix.clear()
        await update.message.reply_text(
            "❌ Процесс создания замеса отменен\n"
            "Для начала нового замеса нажмите /start",
            reply_markup=ReplyKeyboardRemove() # Удаляем клавиатуру
        )
    return ConversationHandler.END

# --- НОВЫЙ БЛОК: FLASK-СЕРВЕР ДЛЯ ПОДДЕРЖАНИЯ АКТИВНОСТИ ---
flask_app = Flask('') # Инициализируем Flask-приложение

@flask_app.route('/')
def keep_alive():
    return "Bot is alive!" # Просто текст, чтобы UptimeRobot знал, что сервер отвечает

def run_flask_app_in_thread():
    # Replit использует порт 8080 для веб-сервера. host='0.0.0.0' делает его доступным извне.
    flask_app.run(host='0.0.0.0', port=8080)
# --- КОНЕЦ НОВОГО БЛОКА ---

def main():
    # --- НОВОЕ: ЗАПУСК FLASK-СЕРВЕРА В ОТДЕЛЬНОМ ПОТОКЕ ---
    # Это должно быть выполнено до запуска Telegram-бота
    flask_thread = Thread(target=run_flask_app_in_thread)
    flask_thread.start()
    logger.info("Flask-сервер запущен в отдельном потоке.")
    # --- КОНЕЦ НОВОГО ---

    app = ApplicationBuilder().token(TOKEN).build()

    # Инициализируем bot_data для хранения pending_mixes
    app.bot_data['pending_mixes'] = {}

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AWAIT_RESPONSIBLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_responsible)],
            AWAIT_PRODUCT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_product_name)],
            AWAIT_RECIPE: [
                MessageHandler(filters.PHOTO, handle_recipe_photo),
                MessageHandler(filters.Text("Отменить"), cancel)
            ],
            AWAIT_INGREDIENT: [
                MessageHandler(filters.PHOTO, handle_ingredient_photo),
                MessageHandler(filters.Text(["Добавить фото", "Следующий ингредиент", "Завершить", "Отменить"]), handle_ingredient_action)
            ],
            CONFIRMATION: [
                MessageHandler(filters.Text("На проверку"), send_for_approval),
                MessageHandler(filters.Text("Отменить"), cancel)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Отдельный ConversationHandler для администраторов
    admin_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_approval, pattern="^(approve|reject_\\d+|reject_custom)_([0-9a-fA-F-]+)$")],
        states={
            AWAIT_CUSTOM_REJECTION_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_rejection_reason),
                CommandHandler('cancel', cancel) # Админ может отменить ввод причины
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)
    app.add_handler(admin_conv_handler) # Добавляем обработчик для админа

    logger.info("Бот запущен")
    print("Бот работает. Нажмите Ctrl+C для остановки") # Это сообщение будет видно в консоли Replit
    app.run_polling()

if __name__ == '__main__':
    main()