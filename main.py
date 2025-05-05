import asyncio
import os
import logging
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

# Holatlar
class QuizStates(StatesGroup):
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
                    if not current_question:  # Savol matni
                        if line.strip():  # Bo‘sh savolni oldini olish
                            current_question = {"question": line, "options": [], "correct": None}
                        else:
                            logger.warning(f"Bo‘sh savol topildi, o‘tkazib yuborildi: liniya {i+1}")
                    else:  # Javob variantlari
                        cleaned_line = line.strip('"')
                        if cleaned_line:  # Bo‘sh variantni oldini olish
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
            # Oxirgi savolni qo‘shish
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
MAX_QUESTIONS = 50  # Har bir quizda 50 ta savol

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
        f"{len(QUESTIONS)} ta savol mavjud. Quizni boshlash uchun /quiz buyrug‘ini yuboring."
    )

@dp.message(Command(commands=["quiz"]))
async def quiz_start(message: types.Message, state: FSMContext):
    if not QUESTIONS:
        await message.reply(
            "❌ Hozirda savollar mavjud emas. Iltimos, savollar faylini tekshiring (barcha_maruza_2_19.txt)."
        )
        return
    # Tugmalar ro‘yxati
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
        "🎯 Quiz boshlanmoqda! Har bir savol uchun qancha vaqt kerak? (soniyalarda)",
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
    
    # Foydalanuvchi uchun ma’lumotlarni boshlash
    user_data[user_id] = {
        "score": 0,
        "wrong": 0,
        "skipped": 0,
        "question_count": 0,
        "active_poll": None,
        "poll_id": None,
        "used_questions": [],
        "time_limit": int(time_choice),
        "consecutive_skips": 0,
        "poll_message_id": None,
        "timeout_task": None
    }
    
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
        await state.finish()
        return
    
    if user_data[user_id]["question_count"] >= MAX_QUESTIONS:
        await show_results(chat_id=chat_id, user_id=user_id)
        user_data.pop(user_id, None)
        await state.finish()
        return
    
    available_questions = [i for i in range(len(QUESTIONS)) if i not in user_data[user_id]["used_questions"]]
    if not available_questions:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Savollar tugadi! Quizni yakunlayman."
        )
        await show_results(chat_id=chat_id, user_id=user_id)
        user_data.pop(user_id, None)
        await state.finish()
        return
    
    question_idx = random.choice(available_questions)
    user_data[user_id]["used_questions"].append(question_idx)
    question = QUESTIONS[question_idx]
    
    # Savol va variantlarni log qilish
    logger.info(f"Savol yuborilmoqda (user_id={user_id}): {question['question']}")
    logger.info(f"Variantlar: {question['options']}")
    
    user_data[user_id]["question_count"] += 1
    user_data[user_id]["active_poll"] = question
    
    # Eski timeout vazifasini bekor qilish
    if user_data[user_id]["timeout_task"] is not None:
        user_data[user_id]["timeout_task"].cancel()
        logger.info(f"Eski timeout vazifasi bekor qilindi: user_id={user_id}")
    
    # Poll yuborish
    try:
        poll = await bot.send_poll(
            chat_id=chat_id,
            question=f"❓ Savol {user_data[user_id]['question_count']}/{MAX_QUESTIONS}: {question['question']}",
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
        
        # Vaqt tugashini kuzatish
        user_data[user_id]["timeout_task"] = asyncio.create_task(
            handle_poll_timeout(chat_id, poll.poll.id, user_data[user_id]["time_limit"], state)
        )
    except Exception as e:
        logger.error(f"Poll yuborishda xato (user_id={user_id}): {e}")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Savolni yuborishda xato yuz berdi. Iltimos, qayta urinib ko‘ring."
        )
        await state.finish()
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
    # Keyingi savolni yuborish
    await send_quiz_question(chat_id=user_id, state=state)

@dp.poll_answer(QuizStates.HANDLE_QUIZ)
async def handle_poll_answer(poll_answer: types.PollAnswer, state: FSMContext):
    user_id = poll_answer.user.id
    poll_id = poll_answer.poll_id
    
    logger.info(f"Poll javobi keldi: user_id={user_id}, poll_id={poll_id}")
    
    if user_id not in user_data or user_data[user_id]["poll_id"] != poll_id:
        logger.warning(f"Noto‘g‘ri user_id yoki poll_id: user_id={user_id}, poll_id={poll_id}")
        return
    
    # Timeout vazifasini bekor qilish
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
    
    # Keyingi savolni yuborish
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
        await state.finish()
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
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🏆 Quiz tugadi!\n"
            f"📊 Natijalar:\n"
            f"  - Umumiy savollar: {total}/{MAX_QUESTIONS}\n"
            f"  - To‘g‘ri javoblar: {score}\n"
            f"  - Noto‘g‘ri javoblar: {wrong}\n"
            f"  - O‘tkazib yuborilgan: {skipped}\n"
            "Yana o‘ynash uchun /quiz buyrug‘ini yuboring!"
        )
    )

@dp.message(Command(commands=["cancel"]))
async def cancel_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in user_data:
        # Timeout vazifasini bekor qilish
        if user_data[user_id]["timeout_task"] is not None:
            user_data[user_id]["timeout_task"].cancel()
            user_data[user_id]["timeout_task"] = None
        await show_results(chat_id=user_id, user_id=user_id)
        user_data.pop(user_id, None)
    await message.reply(
        "⏹ Quiz bekor qilindi. Yana o‘ynash uchun /quiz buyrug‘ini yuboring!",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.finish()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())