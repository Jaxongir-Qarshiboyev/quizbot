import asyncio
import os
import logging
import math
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import random

# Logging sozlash
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# .env faylidan tokenni o‘qish
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBAPP_HOST = os.getenv("HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("PORT", 8000))

# Holatlar
class QuizStates(StatesGroup):
    CHOOSE_MODE = State()
    CHOOSE_GROUP = State()
    CHOOSE_TIME = State()
    HANDLE_QUIZ = State()
    PAUSE = State()

# Savollarni fayldan o‘qish
def load_questions():
    questions = []
    current_question = None
    try:
        with open("barcha_maruza_2_19.txt", "r", encoding="utf-8") as file:
            lines = [line.strip() for line in file.readlines()]
            if not lines:
                logger.error("Fayl bo‘sh: barcha_maruza_2_19.txt")
                return questions

            i = 0
            while i < len(lines):
                line = lines[i]
                if line and line != "+++++" and line != "====":
                    if not current_question:
                        if line.strip():
                            current_question = {"question": line, "options": [], "correct": None}
                        else:
                            logger.warning(f"Bo‘sh savol topildi, o‘tkazib yuborildi: liniya {i+1}")
                    else:
                        cleaned_line = line.strip('"')
                        if cleaned_line:
                            current_question["options"].append(cleaned_line)
                            if line.startswith("#"):
                                current_question["correct"] = len(current_question["options"]) - 1
                                current_question["options"][-1] = cleaned_line[1:] if cleaned_line.startswith("#") else cleaned_line
                        else:
                            logger.warning(f"Bo‘sh variant topildi: liniya {i+1}")
                elif line == "+++++":
                    if current_question and len(current_question["options"]) == 4 and current_question["correct"] is not None:
                        questions.append(current_question)
                    else:
                        logger.warning(f"Noto‘g‘ri formatdagi savol topildi: {current_question}")
                    current_question = None
                i += 1
            if current_question and len(current_question["options"]) == 4 and current_question["correct"] is not None:
                questions.append(current_question)
            else:
                logger.warning(f"Oxirgi savol noto‘g‘ri formatda: {current_question}")
    except FileNotFoundError:
        logger.error("Fayl topilmadi: barcha_maruza_2_19.txt")
    except Exception as e:
        logger.error(f"Faylni o‘qishda xato: {e}")
    logger.info(f"Yuklangan savollar soni: {len(questions)}")
    return questions

# Foydalanuvchi ma’lumotlari
user_data = {}
QUESTIONS = load_questions()
GROUP_SIZE = 30
MAX_QUESTIONS_RANDOM = 50
MAX_QUESTIONS = GROUP_SIZE
TOTAL_GROUPS = math.ceil(len(QUESTIONS) / GROUP_SIZE)

# Botni sozlash
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot=bot, storage=storage)

@dp.message(Command(commands=["start"]))
async def start_command(message: types.Message):
    if not QUESTIONS:
        await message.reply(
            "❌ Hozirda savollar mavjud emas. Iltimos, savollar faylini tekshiring (barcha_maruza_2_19.txt)."
        )
        return
    await message.reply(
        "🎉 JavaScript quiz botga xush kelibsiz! ❓\n"
        f"{len(QUESTIONS)} ta savol mavjud ({TOTAL_GROUPS} guruh, har birida {GROUP_SIZE} gacha savol).\n"
        f"Random rejim: {MAX_QUESTIONS_RANDOM} savol. Tartibli rejim: {GROUP_SIZE} savol.\n"
        "Quizni boshlash uchun /quiz buyrug‘ini yuboring."
    )

@dp.message(Command(commands=["quiz"]))
async def quiz_start(message: types.Message, state: FSMContext):
    if not QUESTIONS:
        await message.reply(
            "❌ Hozirda savollar mavjud emas. Iltimos, savollar faylini tekshiring (barcha_maruza_2_19.txt)."
        )
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Random"), KeyboardButton(text="Tartibli")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.reply(
        "🎯 Quiz boshlanmoqda! Rejimni tanlang: Random (test uchun) yoki Tartibli (o‘rganish uchun).",
        reply_markup=keyboard
    )
    await state.set_state(QuizStates.CHOOSE_MODE)

@dp.message(QuizStates.CHOOSE_MODE)
async def choose_mode(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    mode = message.text
    if mode not in ["Random", "Tartibli"]:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Random"), KeyboardButton(text="Tartibli")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.reply(
            "❌ Iltimos, 'Random' yoki 'Tartibli' ni tanlang!",
            reply_markup=keyboard
        )
        return
    
    user_data[user_id] = {
        "mode": mode,
        "score": 0,
        "wrong": 0,
        "skipped": 0,
        "question_count": 0,
        "active_poll": None,
        "poll_id": None,
        "used_questions": [],
        "time_limit": None,
        "consecutive_skips": 0,
        "poll_message_id": None,
        "timeout_task": None,
        "start_index": 0,
        "group_number": None
    }
    
    logger.info(f"Rejim tanlandi: user_id={user_id}, mode={mode}")
    
    if mode == "Tartibli":
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=str(i)) for i in range(1, min(4, TOTAL_GROUPS + 1))],
                [KeyboardButton(text=str(i)) for i in range(4, min(7, TOTAL_GROUPS + 1))] if TOTAL_GROUPS > 3 else [],
                [KeyboardButton(text=str(i)) for i in range(7, TOTAL_GROUPS + 1)] if TOTAL_GROUPS > 6 else []
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.reply(
            f"📚 Tartibli rejim tanlandi. {TOTAL_GROUPS} ta guruh mavjud (har birida {GROUP_SIZE} gacha savol).\n"
            "Qaysi guruhni tanlaysiz? (1-guruh: 1-30, 2-guruh: 31-60, ...)",
            reply_markup=keyboard
        )
        await state.set_state(QuizStates.CHOOSE_GROUP)
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="5"), KeyboardButton(text="10"), KeyboardButton(text="15")],
                [KeyboardButton(text="20"), KeyboardButton(text="30"), KeyboardButton(text="45")],
                [KeyboardButton(text="60")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.reply(
            "⏳ Har bir savol uchun qancha vaqt kerak? (soniyalarda)",
            reply_markup=keyboard
        )
        await state.set_state(QuizStates.CHOOSE_TIME)

@dp.message(QuizStates.CHOOSE_GROUP)
async def choose_group(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        group_number = int(message.text)
        if group_number < 1 or group_number > TOTAL_GROUPS:
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=str(i)) for i in range(1, min(4, TOTAL_GROUPS + 1))],
                    [KeyboardButton(text=str(i)) for i in range(4, min(7, TOTAL_GROUPS + 1))] if TOTAL_GROUPS > 3 else [],
                    [KeyboardButton(text=str(i)) for i in range(7, TOTAL_GROUPS + 1)] if TOTAL_GROUPS > 6 else []
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            await message.reply(
                f"❌ Iltimos, 1 dan {TOTAL_GROUPS} gacha bo‘lgan guruh raqamini tanlang!",
                reply_markup=keyboard
            )
            return
        user_data[user_id]["group_number"] = group_number
        user_data[user_id]["start_index"] = (group_number - 1) * GROUP_SIZE
        logger.info(f"Guruh tanlandi: user_id={user_id}, group_number={group_number}, start_index={user_data[user_id]['start_index']}")
    except ValueError:
        await message.reply(
            "❌ Iltimos, faqat raqam kiriting!"
        )
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="5"), KeyboardButton(text="10"), KeyboardButton(text="15")],
            [KeyboardButton(text="20"), KeyboardButton(text="30"), KeyboardButton(text="45")],
            [KeyboardButton(text="60")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.reply(
        f"⏳ Guruh {group_number} tanlandi ({user_data[user_id]['start_index'] + 1}-{min(user_data[user_id]['start_index'] + GROUP_SIZE, len(QUESTIONS))} savollar).\n"
        "Har bir savol uchun qancha vaqt kerak? (soniyalarda)",
        reply_markup=keyboard
    )
    await state.set_state(QuizStates.CHOOSE_TIME)

@dp.message(QuizStates.CHOOSE_TIME)
async def choose_time(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    time_choice = message.text
    if time_choice not in ["5", "10", "15", "20", "30", "45", "60"]:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="5"), KeyboardButton(text="10"), KeyboardButton(text="15")],
                [KeyboardButton(text="20"), KeyboardButton(text="30"), KeyboardButton(text="45")],
                [KeyboardButton(text="60")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.reply(
            "❌ Iltimos, 5, 10, 15, 20, 30, 45 yoki 60 soniyadan birini tanlang!",
            reply_markup=keyboard
        )
        return
    
    user_data[user_id]["time_limit"] = int(time_choice)
    
    await message.reply(
        f"⏳ Har bir savol uchun {time_choice} soniya vaqt beriladi. Birinchi savol keladi...",
        reply_markup=ReplyKeyboardRemove()
    )
    await send_quiz_question(chat_id=message.chat.id, state=state)
    await state.set_state(QuizStates.HANDLE_QUIZ)

async def send_quiz_question(chat_id: int, state: FSMContext):
    user_id = chat_id
    if user_id not in user_data:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Iltimos, quizni /quiz buyrug‘i bilan boshlang!"
        )
        await state.clear()
        return
    
    max_questions = MAX_QUESTIONS_RANDOM if user_data[user_id]["mode"] == "Random" else MAX_QUESTIONS
    
    if user_data[user_id]["question_count"] >= max_questions:
        await show_results(chat_id=chat_id, user_id=user_id)
        user_data.pop(user_id, None)
        await state.clear()
        return
    
    if user_data[user_id]["mode"] == "Random":
        available_questions = [i for i in range(len(QUESTIONS)) if i not in user_data[user_id]["used_questions"]]
        if not available_questions:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Savollar tugadi! Quizni yakunlayman."
            )
            await show_results(chat_id=chat_id, user_id=user_id)
            user_data.pop(user_id, None)
            await state.clear()
            return
        question_idx = random.choice(available_questions)
    else:
        question_idx = user_data[user_id]["start_index"] + user_data[user_id]["question_count"]
        if question_idx >= len(QUESTIONS):
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Tanlangan guruhda savollar tugadi! Quizni yakunlayman."
            )
            await show_results(chat_id=chat_id, user_id=user_id)
            user_data.pop(user_id, None)
            await state.clear()
            return
    
    user_data[user_id]["used_questions"].append(question_idx)
    question = QUESTIONS[question_idx]
    
    logger.info(f"Savol yuborilmoqda (user_id={user_id}, mode={user_data[user_id]['mode']}, idx={question_idx}): {question['question']}")
    logger.info(f"Variantlar: {question['options']}")
    
    user_data[user_id]["question_count"] += 1
    user_data[user_id]["active_poll"] = question
    
    if user_data[user_id]["timeout_task"] is not None:
        user_data[user_id]["timeout_task"].cancel()
        logger.info(f"Eski timeout vazifasi bekor qilindi: user_id={user_id}")
    
    try:
        poll = await bot.send_poll(
            chat_id=chat_id,
            question=f"❓ Savol {user_data[user_id]['question_count']}/{max_questions}: {question['question']}",
            options=question["options"],
            type="quiz",
            correct_option_id=question["correct"],
            is_anonymous=False,
            open_period=user_data[user_id]["time_limit"],
            explanation=f"✅ To‘g‘ri javob: {question['options'][question['correct']]}"
        )
        user_data[user_id]["poll_id"] = poll.poll.id
        user_data[user_id]["poll_message_id"] = poll.message_id
        logger.info(f"Poll yuborildi: poll_id={poll.poll.id}, message_id={poll.message_id}")
        
        user_data[user_id]["timeout_task"] = asyncio.create_task(
            handle_poll_timeout(chat_id, poll.poll.id, user_data[user_id]["time_limit"], state)
        )
    except Exception as e:
        logger.error(f"Poll yuborishda xato (user_id={user_id}): {e}")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Savolni yuborishda xato yuz berdi. Iltimos, qayta urinib ko‘ring."
        )
        await state.clear()
        return

async def handle_poll_timeout(chat_id: int, poll_id: str, time_limit: int, state: FSMContext):
    user_id = chat_id
    logger.info(f"Vaqt kuzatilmoqda: user_id={user_id}, poll_id={poll_id}, time_limit={time_limit}")
    
    try:
        await asyncio.sleep(time_limit)
    except asyncio.CancelledError:
        logger.info(f"Timeout vazifasi bekor qilindi: user_id={user_id}, poll_id={poll_id}")
        return
    
    if user_id not in user_data or user_data[user_id]["poll_id"] != poll_id:
        logger.info(f"Vaqt tugashi e’tiborsiz qoldirildi: user_id={user_id}, poll_id={poll_id}")
        return
    
    user_data[user_id]["timeout_task"] = None
    user_data[user_id]["skipped"] += 1
    user_data[user_id]["consecutive_skips"] += 1
    
    logger.info(f"Savol o‘tkazib yuborildi: user_id={user_id}, consecutive_skips={user_data[user_id]['consecutive_skips']}")
    
    if user_data[user_id]["consecutive_skips"] >= 3:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Davom ettirish"), KeyboardButton(text="Tugatish")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await bot.send_message(
            chat_id=user_id,
            text="⏸ Ketma-ket 3 ta savol o‘tkazib yuborildi. Quiz pauza qilindi.\nDavom ettirish yoki tugatishni tanlang:",
            reply_markup=keyboard
        )
        await state.set_state(QuizStates.PAUSE)
        return
    
    await bot.send_message(
        chat_id=user_id,
        text="⏰ Vaqt tugadi! Bu savol o‘tkazib yuborildi."
    )
    await send_quiz_question(chat_id=user_id, state=state)

@dp.poll_answer(QuizStates.HANDLE_QUIZ)
async def handle_poll_answer(poll_answer: types.PollAnswer, state: FSMContext):
    user_id = poll_answer.user.id
    poll_id = poll_answer.poll_id
    
    logger.info(f"Poll javobi keldi: user_id={user_id}, poll_id={poll_id}")
    
    if user_id not in user_data or user_data[user_id]["poll_id"] != poll_id:
        logger.warning(f"Noto‘g‘ri user_id yoki poll_id: user_id={user_id}, poll_id={poll_id}")
        return
    
    if user_data[user_id]["timeout_task"] is not None:
        user_data[user_id]["timeout_task"].cancel()
        user_data[user_id]["timeout_task"] = None
        logger.info(f"Timeout vazifasi javob tufayli bekor qilindi: user_id={user_id}, poll_id={poll_id}")
    
    correct_option = user_data[user_id]["active_poll"]["correct"]
    selected_option = poll_answer.option_ids[0] if poll_answer.option_ids else None
    
    user_data[user_id]["consecutive_skips"] = 0
    
    try:
        if selected_option == correct_option:
            user_data[user_id]["score"] += 1
            await bot.send_message(
                chat_id=user_id,
                text="🎯 To‘g‘ri javob!"
            )
        else:
            user_data[user_id]["wrong"] += 1
            correct_answer = user_data[user_id]["active_poll"]["options"][correct_option]
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ Noto‘g‘ri! To‘g‘ri javob: {correct_answer}"
            )
    except Exception as e:
        logger.error(f"Javobni qayta ishlashda xato (user_id={user_id}): {e}")
    
    await send_quiz_question(chat_id=user_id, state=state)

@dp.message(QuizStates.PAUSE)
async def pause_choice(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    choice = message.text
    
    if choice == "Davom ettirish":
        user_data[user_id]["consecutive_skips"] = 0
        await message.reply(
            "▶️ Quiz davom ettirilmoqda...",
            reply_markup=ReplyKeyboardRemove()
        )
        await send_quiz_question(chat_id=user_id, state=state)
        await state.set_state(QuizStates.HANDLE_QUIZ)
    elif choice == "Tugatish":
        await show_results(chat_id=user_id, user_id=user_id)
        user_data.pop(user_id, None)
        await state.clear()
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Davom ettirish"), KeyboardButton(text="Tugatish")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.reply(
            "❌ Iltimos, 'Davom ettirish' yoki 'Tugatish' ni tanlang!",
            reply_markup=keyboard
        )

async def show_results(chat_id: int, user_id: int):
    score = user_data[user_id]["score"]
    wrong = user_data[user_id]["wrong"]
    skipped = user_data[user_id]["skipped"]
    total = user_data[user_id]["question_count"]
    mode = user_data[user_id]["mode"]
    max_questions = MAX_QUESTIONS_RANDOM if mode == "Random" else MAX_QUESTIONS
    extra_info = ""
    if mode == "Tartibli":
        group_number = user_data[user_id]["group_number"]
        last_index = user_data[user_id]["start_index"] + total
        extra_info = f"\nGuruh: {group_number} ({user_data[user_id]['start_index'] + 1}-{last_index} savollar).\n"
        next_group = group_number + 1 if last_index < len(QUESTIONS) else None
        if next_group:
            extra_info += f"Keyingi sesiyada {next_group}-guruh ({last_index + 1}-{min(last_index + GROUP_SIZE, len(QUESTIONS))}) ni tanlashingiz mumkin."
        else:
            extra_info += "Bu oxirgi guruh edi!"
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🏆 Quiz tugadi! (Rejim: {mode})\n"
            f"📊 Natijalar:\n"
            f"  - Umumiy savollar: {total}/{max_questions}\n"
            f"  - To‘g‘ri javoblar: {score}\n"
            f"  - Noto‘g‘ri javoblar: {wrong}\n"
            f"  - O‘tkazib yuborilgan: {skipped}\n"
            f"{extra_info}\n"
            "Yana o‘ynash uchun /quiz buyrug‘ini yuboring!"
        )
    )

@dp.message(Command(commands=["cancel"]))
async def cancel_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in user_data:
        if user_data[user_id]["timeout_task"] is not None:
            user_data[user_id]["timeout_task"].cancel()
            user_data[user_id]["timeout_task"] = None
        await show_results(chat_id=user_id, user_id=user_id)
        user_data.pop(user_id, None)
    await message.reply(
        "⏹ Quiz bekor qilindi. Yana o‘ynash uchun /quiz buyrug‘ini yuboring!",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()

# Webhook sozlamalari
async def on_startup(_):
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook o‘rnatildi: {WEBHOOK_URL}")

async def on_shutdown(_):
    await bot.delete_webhook()
    logger.info("Webhook o‘chirildi")

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    asyncio.run(dp.start_webhook(
        webhook_path="",
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True
    ))
