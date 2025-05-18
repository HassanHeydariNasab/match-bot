import logging
import random
from typing import TypedDict, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

ITEMS = ["🍓", "🍓", "🍓", "🍌", "🍌", "🍌", "🍉", "🍉", "🍉"]
BOARD_SIZE_X = 3
BOARD_SIZE_Y = 3


CellInfo = TypedDict(
    "CellInfo", {"value": str, "revealed": bool, "permanently_revealed": bool}
)

SelectedItem = TypedDict("SelectedItem", {"id": str, "value": str})


BoardCells = Dict[str, CellInfo]


def get_initial_board_state() -> BoardCells:
    """Initializes and returns a new board state."""
    random.shuffle(ITEMS)
    board_cells: BoardCells = {}
    idx = 0
    for y in range(1, BOARD_SIZE_Y + 1):
        for x in range(1, BOARD_SIZE_X + 1):
            cell_id = f"{x}_{y}"
            board_cells[cell_id] = {
                "value": ITEMS[idx],
                "revealed": False,
                "permanently_revealed": False,
            }
            idx += 1
    return board_cells


def generate_keyboard(board_cells: BoardCells) -> InlineKeyboardMarkup:
    """Generates the InlineKeyboardMarkup based on the current board_cells state."""
    keyboard = []
    for y in range(1, BOARD_SIZE_Y + 1):
        row = []
        for x in range(1, BOARD_SIZE_X + 1):
            cell_id = f"{x}_{y}"
            cell = board_cells[cell_id]
            if cell["revealed"] or cell["permanently_revealed"]:
                text = cell["value"]
            else:
                text = "❓"
            row.append(InlineKeyboardButton(text, callback_data=cell_id))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat is not None and update.effective_user is not None:
        if context.user_data is None:
            context.user_data = {}
        initial_board = get_initial_board_state()
        context.user_data["board_cells"] = initial_board
        context.user_data["current_selection"] = []
        context.user_data["matched_values"] = []

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"سلام {update.effective_user.first_name}, سه‌تا مثل هم پیدا کن!",
            reply_markup=generate_keyboard(context.user_data["board_cells"]),
        )
    else:
        logging.warning(
            "Start command received without effective_chat or effective_user."
        )


async def button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        logging.warning("Callback query is None.")
        return

    await query.answer()  # Acknowledge callback query

    if context.user_data is None:
        context.user_data = {}

    board_cells: BoardCells | None = context.user_data.get("board_cells")
    current_selection: list[SelectedItem] | None = context.user_data.get(
        "current_selection"
    )
    matched_values: list[str] | None = context.user_data.get("matched_values")

    user_name = "رفیق"
    if update.effective_user and update.effective_user.first_name:
        user_name = update.effective_user.first_name

    default_message_text = f"سلام {user_name}, سه‌تا مثل هم پیدا کن!"

    if board_cells is None or current_selection is None or matched_values is None:
        logging.warning(f"Game state not found in user_data for user {user_name}.")
        error_message = (
            "بازی منقضی شده یا مشکلی پیش آمده. لطفاً با /start یک بازی جدید شروع کنید."
        )
        if isinstance(query.message, Message):
            try:
                await query.edit_message_text(text=error_message)
            except Exception as e_edit:
                logging.error(f"Error editing message for missing game state: {e_edit}")
                if update.effective_chat:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id, text=error_message
                    )
        elif update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text=error_message
            )
        return

    cell_id = query.data
    if cell_id is None or cell_id not in board_cells:
        logging.warning(f"Invalid cell_id: {cell_id} from callback query.")
        return

    tapped_cell_info = board_cells[cell_id]

    if tapped_cell_info["permanently_revealed"] or any(
        sel_item["id"] == cell_id for sel_item in current_selection
    ):
        return

    tapped_cell_info["revealed"] = True
    current_selection.append({"id": cell_id, "value": tapped_cell_info["value"]})

    message_text = default_message_text

    if len(current_selection) == 3:
        is_match = (
            current_selection[0]["value"]
            == current_selection[1]["value"]
            == current_selection[2]["value"]
        )

        if is_match:
            matched_value = current_selection[0]["value"]
            if matched_value not in matched_values:
                matched_values.append(matched_value)

            for item in current_selection:
                board_cells[item["id"]]["permanently_revealed"] = True
                board_cells[item["id"]]["revealed"] = True

            current_selection.clear()

            if len(matched_values) == len(set(ITEMS)):
                message_text = "🎉 برنده شدی! همه رو پیدا کردی! 🎉"
            else:
                message_text = (
                    f"✅ عالی بود! سه تا {matched_value} پیدا کردی. ادامه بده!"
                )

        else:
            for item in current_selection:
                board_cells[item["id"]]["revealed"] = False
            current_selection.clear()
            message_text = "❌ مثل هم نبودن! دوباره تلاش کن."

    # Update context.user_data
    context.user_data["board_cells"] = board_cells
    context.user_data["current_selection"] = current_selection
    context.user_data["matched_values"] = matched_values

    # Edit the message with the updated board
    if isinstance(query.message, Message):
        try:
            current_keyboard_str = (
                str(query.message.reply_markup) if query.message.reply_markup else ""
            )
            new_keyboard_str = str(generate_keyboard(board_cells))

            if (
                query.message.text != message_text
                or current_keyboard_str != new_keyboard_str
            ):
                await query.edit_message_text(
                    text=message_text,
                    reply_markup=generate_keyboard(board_cells),
                )
        except Exception as e:
            logging.error(f"Error editing message: {e}")
            if query.message.text != message_text and update.effective_chat:
                logging.info(
                    f"Falling back to sending new message for chat {update.effective_chat.id}"
                )
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=message_text,
                        reply_markup=generate_keyboard(board_cells),
                    )
                except Exception as e_send:
                    logging.error(f"Error sending fallback message: {e_send}")
    elif (
        update.effective_chat
    ):  # Fallback if query.message is None or InaccessibleMessage
        logging.info(
            f"query.message was not a usable Message instance. Sending new message to chat {update.effective_chat.id}"
        )
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=message_text,
                reply_markup=generate_keyboard(board_cells),
            )
        except Exception as e_send_alt:
            logging.error(f"Error sending new message (fallback): {e_send_alt}")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (update.effective_chat is not None) and (update.message is not None):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="برای شروع دوباره /start رو بزن",
        )
    else:
        pass


if __name__ == "__main__":
    application = (
        ApplicationBuilder()
        .token("233480586:AAGxsvGafJMK0FKuvhfwuA-bgB2Pu7gHbLA")
        .build()
    )

    start_handler = CommandHandler("start", start)
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)
    button_handler = CallbackQueryHandler(button_tap)

    application.add_handler(start_handler)
    application.add_handler(message_handler)
    application.add_handler(button_handler)

    application.run_polling()
