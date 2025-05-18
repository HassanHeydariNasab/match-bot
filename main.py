import logging
import random
import re  # For parsing dimensions
from typing import TypedDict, Dict, List, cast

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# State definitions for ConversationHandler
CHOOSE_DIMENSIONS, CHOOSE_MATCH_COUNT = range(2)

# Emoji pool for dynamic item generation
EMOJI_POOL = [
    "🍓",
    "🍌",
    "🍉",
    "🍇",
    "🥝",
    "🍍",
    "🍑",
    "🍒",
    "🥭",
    "🥥",
    "🥑",
    "🍆",
    "🍅",
    "🌶️",
    "🥕",
    "🌽",
    "🥦",
    "🍄",
    "🥜",
    "🌰",
    "🍞",
    "🥐",
    "🥨",
    "🥯",
    "🥞",
    "🧇",
    "🧀",
    "🍖",
    "🍗",
    "🥩",
    "🍔",
    "🍟",
    "🍕",
    "🌭",
    "🥪",
    "🌮",
]


CellInfo = TypedDict(
    "CellInfo", {"value": str, "revealed": bool, "permanently_revealed": bool}
)

SelectedItem = TypedDict("SelectedItem", {"id": str, "value": str})

BoardCells = Dict[str, CellInfo]


def generate_dynamic_items(
    board_size_x: int, board_size_y: int, match_count: int
) -> List[str] | None:
    """Generates the list of items based on board size and match count."""
    total_cells = board_size_x * board_size_y
    if total_cells % match_count != 0:
        logging.error("Total cells not divisible by match count.")
        return None  # Should be caught by earlier validation

    num_unique_item_sets = total_cells // match_count
    if (
        num_unique_item_sets <= 1 and total_cells > 0
    ):  # Need at least 2 unique sets for a game
        logging.warning(
            f"Not enough unique item sets possible: {num_unique_item_sets} for {total_cells} cells and {match_count} match_count."
        )
        return None

    if num_unique_item_sets > len(EMOJI_POOL):
        logging.warning(
            "Not enough emojis in EMOJI_POOL for the required number of unique items."
        )
        return None  # Not enough unique emojis

    items = []
    for i in range(num_unique_item_sets):
        items.extend([EMOJI_POOL[i]] * match_count)

    random.shuffle(items)
    return items


def get_initial_board_state(
    context: ContextTypes.DEFAULT_TYPE,
) -> BoardCells | None:  # Now takes context
    """Initializes and returns a new board state using parameters from context."""
    if context.user_data is None:  # Should be initialized by PTB
        logging.error("user_data is None in get_initial_board_state")
        return None

    board_size_x = context.user_data.get("board_size_x")
    board_size_y = context.user_data.get("board_size_y")
    match_count = context.user_data.get("match_count")

    if (
        not isinstance(board_size_x, int)
        or not isinstance(board_size_y, int)
        or not isinstance(match_count, int)
    ):
        logging.error(
            "Board dimensions or match count are invalid or not found in user_data."
        )
        return None

    items = generate_dynamic_items(board_size_x, board_size_y, match_count)
    if items is None:
        logging.error("Failed to generate dynamic items for the board.")
        return None

    context.user_data["game_items"] = items

    board_cells: BoardCells = {}
    idx = 0
    # Cast is safe here due to the isinstance checks above
    for y in range(1, cast(int, board_size_y) + 1):
        for x in range(1, cast(int, board_size_x) + 1):
            cell_id = f"{x}_{y}"
            if idx < len(items):
                board_cells[cell_id] = {
                    "value": items[idx],
                    "revealed": False,
                    "permanently_revealed": False,
                }
                idx += 1
            else:
                # This should not happen if total_cells % match_count == 0 and items are generated correctly
                logging.error("Mismatch between generated items and board cells.")
                return None
    return board_cells


def generate_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
) -> InlineKeyboardMarkup | None:  # Now takes context
    """Generates the InlineKeyboardMarkup based on the current board_cells state."""
    if context.user_data is None:
        logging.error("user_data is None in generate_keyboard")
        return None

    board_cells = context.user_data.get("board_cells")
    board_size_x = context.user_data.get("board_size_x")
    board_size_y = context.user_data.get("board_size_y")

    if (
        not isinstance(board_cells, dict)
        or not isinstance(board_size_x, int)
        or not isinstance(board_size_y, int)
    ):
        logging.error("Board data missing or invalid for keyboard generation.")
        return None

    # Ensure board_cells is treated as BoardCells
    current_board_cells = cast(BoardCells, board_cells)

    keyboard = []
    # Casts are safe here due to isinstance checks
    for y in range(1, cast(int, board_size_y) + 1):
        row = []
        for x in range(1, cast(int, board_size_x) + 1):
            cell_id = f"{x}_{y}"
            cell = current_board_cells[cell_id]  # Use the casted variable
            if cell["revealed"] or cell["permanently_revealed"]:
                text = cell["value"]
            else:
                text = "❓"
            row.append(InlineKeyboardButton(text, callback_data=cell_id))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the game configuration conversation."""
    if update.effective_chat:
        await update.effective_chat.send_message(
            "به بازی پیدا کردن آیتم‌های مشابه خوش آمدید!\n"
            "لطفاً ابعاد تخته بازی را وارد کنید (مثلاً 3x3 یا 4x2)."
        )
    return CHOOSE_DIMENSIONS


async def choose_dimensions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles user input for board dimensions."""
    if not update.message or not update.message.text:
        if update.effective_chat:
            await update.effective_chat.send_message("لطفاً ابعاد را وارد کنید.")
        return CHOOSE_DIMENSIONS

    user_input = update.message.text
    match = re.fullmatch(r"(\d+)[xX×](\d+)", user_input)

    if not match:
        if update.effective_chat:
            await update.effective_chat.send_message(
                "فرمت نامعتبر است. لطفاً ابعاد را به صورت XxY وارد کنید (مثلاً 3x3)."
            )
        return CHOOSE_DIMENSIONS

    x_dim, y_dim = int(match.group(1)), int(match.group(2))

    if x_dim > 8 or y_dim > 9:
        if update.effective_chat:
            await update.effective_chat.send_message(
                "ابعاد نامعتبر است. حداکثر 8x9 مجاز است."
            )
        return CHOOSE_DIMENSIONS

    if not (
        1 < x_dim * y_dim <= len(EMOJI_POOL) * 10 and x_dim > 0 and y_dim > 0
    ):  # Max 10 items per emoji type, min 2 cells
        if update.effective_chat:
            await update.effective_chat.send_message(
                "ابعاد نامعتبر است. حداقل باید ۲ خانه داشته باشد و ابعاد معقول باشد."
            )
        return CHOOSE_DIMENSIONS

    if x_dim * y_dim > 100:  # Arbitrary limit for very large boards
        if update.effective_chat:
            await update.effective_chat.send_message(
                "ابعاد تخته خیلی بزرگ است. لطفاً یک ابعاد کوچکتر انتخاب کنید."
            )
        return CHOOSE_DIMENSIONS

    if context.user_data is None:
        logging.error("user_data is None in choose_dimensions")
        return CHOOSE_DIMENSIONS

    context.user_data["board_size_x"] = x_dim
    context.user_data["board_size_y"] = y_dim

    if update.effective_chat:
        await update.effective_chat.send_message(
            f"عالی! ابعاد تخته {x_dim}x{y_dim} انتخاب شد.\n"
            "حالا تعداد آیتم‌هایی که برای تشکیل یک گروه مشابه لازم است را وارد کنید (مثلاً 3)."
        )
    return CHOOSE_MATCH_COUNT


async def choose_match_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles user input for the number of items to match."""
    if not update.message or not update.message.text:
        if update.effective_chat:
            await update.effective_chat.send_message(
                "لطفاً تعداد آیتم برای تطابق را وارد کنید."
            )
        return CHOOSE_MATCH_COUNT

    user_input = update.message.text
    if context.user_data is None:  # Should be initialized
        logging.error("user_data is None in choose_match_count beginning")
        if update.effective_chat:
            await update.effective_chat.send_message(
                "مشکلی پیش آمده (اطلاعات کاربر یافت نشد)، لطفاً با /start مجدداً شروع کنید."
            )
        return ConversationHandler.END

    board_size_x = context.user_data.get("board_size_x")
    board_size_y = context.user_data.get("board_size_y")

    if not isinstance(board_size_x, int) or not isinstance(board_size_y, int):
        logging.error(
            "Board dimensions not found or invalid in user_data for choose_match_count."
        )
        if update.effective_chat:
            await update.effective_chat.send_message(
                "مشکلی پیش آمده (ابعاد تخته نامشخص است)، لطفاً با /start مجدداً شروع کنید."
            )
        return ConversationHandler.END

    try:
        match_count = int(user_input)
    except ValueError:
        if update.effective_chat:
            await update.effective_chat.send_message(
                "عدد وارد شده نامعتبر است. لطفاً یک عدد صحیح وارد کنید."
            )
        return CHOOSE_MATCH_COUNT

    # board_size_x and board_size_y were assigned from context.user_data.get()
    # and confirmed to be integers by the isinstance check above.
    # We directly use these validated local variables.
    total_cells = board_size_x * board_size_y

    if not (1 < match_count <= total_cells):
        if update.effective_chat:
            await update.effective_chat.send_message(
                f"تعداد آیتم برای تطابق باید بیشتر از 1 و کمتر یا مساوی تعداد کل خانه‌ها ({total_cells}) باشد."
            )
        return CHOOSE_MATCH_COUNT

    if total_cells % match_count != 0:
        if update.effective_chat:
            await update.effective_chat.send_message(
                f"تعداد کل خانه‌ها ({total_cells}) باید بر تعداد آیتم برای تطابق ({match_count}) بخش‌پذیر باشد."
            )
        return CHOOSE_MATCH_COUNT

    num_unique_item_sets = total_cells // match_count
    if (
        num_unique_item_sets <= 1 and total_cells > 1
    ):  # Need at least 2 unique sets for a game unless it's a 1-cell board (which is invalid anyway)
        if update.effective_chat:
            await update.effective_chat.send_message(
                "با این تنظیمات، کمتر از دو گروه منحصر به فرد از آیتم‌ها خواهیم داشت. لطفاً تعداد تطابق را تغییر دهید یا ابعاد را بزرگتر کنید."
            )
        return CHOOSE_MATCH_COUNT

    if num_unique_item_sets > len(EMOJI_POOL):
        if update.effective_chat:
            await update.effective_chat.send_message(
                f"متاسفانه به تعداد کافی ({num_unique_item_sets}) شکلک منحصر به فرد برای این تنظیمات نداریم. "
                f"حداکثر {len(EMOJI_POOL)} گروه منحصر به فرد امکان‌پذیر است. "
                "لطفاً ابعاد را کوچکتر یا تعداد تطابق را بیشتر کنید."
            )
        return CHOOSE_MATCH_COUNT

    context.user_data["match_count"] = match_count

    # Initialize board state
    initial_board_cells = get_initial_board_state(context)
    if initial_board_cells is None:
        # This indicates an issue with item generation based on validated parameters, which should be rare.
        if update.effective_chat:
            await update.effective_chat.send_message(
                "مشکلی در ساخت تخته بازی پیش آمد. لطفاً با /start مجدداً تلاش کنید."
            )
        return ConversationHandler.END

    context.user_data["board_cells"] = initial_board_cells
    context.user_data["current_selection"] = []
    context.user_data[
        "matched_values"
    ] = []  # Stores values of successfully matched sets

    reply_markup = generate_keyboard(context)

    if update.effective_chat and reply_markup:
        await update.effective_chat.send_message(
            text=f"بازی شروع شد! {match_count} تا مثل هم پیدا کن!",
            reply_markup=reply_markup,
        )
    elif (
        update.effective_chat
    ):  # Fallback if keyboard generation failed (should be rare)
        await update.effective_chat.send_message(
            "مشکلی در نمایش تخته بازی پیش آمد. لطفاً با /start مجدداً تلاش کنید."
        )

    return ConversationHandler.END


async def button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        logging.warning("Callback query is None.")
        return

    await query.answer()

    if context.user_data is None:
        context.user_data = {}  # Should be initialized

    board_cells: BoardCells | None = context.user_data.get("board_cells")
    current_selection: list[SelectedItem] | None = context.user_data.get(
        "current_selection"
    )
    matched_values: list[str] | None = context.user_data.get("matched_values")
    match_count: int | None = context.user_data.get("match_count")
    game_items: list[str] | None = context.user_data.get("game_items")

    if (
        board_cells is None
        or current_selection is None
        or matched_values is None
        or match_count is None
        or game_items is None
    ):
        logging.warning("Game state not found in user_data in button_tap.")
        error_message = (
            "بازی منقضی شده یا مشکلی پیش آمده. لطفاً با /start یک بازی جدید شروع کنید."
        )
        # Attempt to edit message or send a new one
        if isinstance(query.message, Message):
            try:
                await query.edit_message_text(text=error_message)
            except Exception as e_edit:
                logging.error(f"Error editing message for missing game state: {e_edit}")
                if update.effective_chat:  # Fallback to sending a new message
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id, text=error_message
                    )
        elif (
            update.effective_chat
        ):  # If query.message is not a Message, try sending new
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text=error_message
            )
        return

    default_message_text = f"{match_count} تا مثل هم پیدا کن!"
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

    if len(current_selection) == match_count:
        # Check if all selected items have the same value
        is_match = len(set(item["value"] for item in current_selection)) == 1

        if is_match:
            matched_value = current_selection[0]["value"]
            if (
                matched_value not in matched_values
            ):  # Only add unique values to track unique sets
                matched_values.append(matched_value)

            for item in current_selection:
                board_cells[item["id"]]["permanently_revealed"] = True
                board_cells[item["id"]]["revealed"] = True

            current_selection.clear()

            # Win condition: all unique item types have been matched
            num_unique_item_types = len(set(game_items))
            if len(matched_values) == num_unique_item_types:
                message_text = "🎉 برنده شدی! همه رو پیدا کردی! 🎉"
            else:
                message_text = f"✅ عالی بود! {match_count} تا {matched_value} پیدا کردی. ادامه بده!"
        else:
            for item in current_selection:
                board_cells[item["id"]]["revealed"] = False
            current_selection.clear()
            message_text = (
                f"❌ مثل هم نبودن! ({match_count} تا باید مثل هم باشن). دوباره تلاش کن."
            )

    context.user_data["board_cells"] = board_cells
    context.user_data["current_selection"] = current_selection
    context.user_data["matched_values"] = matched_values

    reply_markup = generate_keyboard(context)
    if reply_markup is None:  # Should not happen if state is consistent
        logging.error(
            "Failed to generate keyboard in button_tap, possibly due to missing user_data."
        )
        if isinstance(query.message, Message) and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="مشکلی در به‌روزرسانی تخته بازی پیش آمد.",
            )
        return

    if isinstance(query.message, Message):
        try:
            current_keyboard_str = (
                str(query.message.reply_markup) if query.message.reply_markup else ""
            )
            new_keyboard_str = str(reply_markup)

            if (
                query.message.text != message_text
                or current_keyboard_str != new_keyboard_str
            ):
                await query.edit_message_text(
                    text=message_text,
                    reply_markup=reply_markup,
                )
        except Exception as e:
            logging.error(f"Error editing message: {e}")
            if (
                query.message.text != message_text and update.effective_chat
            ):  # Fallback on text change
                logging.info(
                    f"Falling back to sending new message for chat {update.effective_chat.id}"
                )
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=message_text,
                        reply_markup=reply_markup,
                    )
                except Exception as e_send:
                    logging.error(f"Error sending fallback message: {e_send}")
    elif update.effective_chat:
        logging.info(
            f"query.message was not a usable Message instance. Sending new message to chat {update.effective_chat.id}"
        )
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=message_text,
                reply_markup=reply_markup,
            )
        except Exception as e_send_alt:
            logging.error(f"Error sending new message (fallback): {e_send_alt}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    if update.effective_user:
        if update.effective_chat:
            await update.effective_chat.send_message(
                "هر وقت خواستی دوباره بازی کنی، دستور /start رو بفرست."
            )
    if context.user_data is not None:
        context.user_data.clear()
    return ConversationHandler.END


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This handler is now less relevant if most interactions are within conversations or button taps
    # It can be used for messages outside of active conversations.
    if update.effective_chat and update.message and update.message.text:
        # If not in a conversation, and not a command, guide the user.
        if not context.user_data or not any(
            k in context.user_data for k in ["board_size_x", "match_count"]
        ):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="برای شروع بازی جدید، لطفاً دستور /start را ارسال کنید.",
            )
        # else: if in a game (e.g. board_cells exists), could ignore or remind about game.
        # For now, let's keep it simple and only suggest /start if no game config is found.


if __name__ == "__main__":
    application = (
        ApplicationBuilder()
        .token("233480586:AAGxsvGafJMK0FKuvhfwuA-bgB2Pu7gHbLA")
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_DIMENSIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_dimensions)
            ],
            CHOOSE_MATCH_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_match_count)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        # Optionally: allow_reentry=True
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_tap))
    # The generic message handler is now less critical but can catch stray messages.
    # Ensure it doesn't interfere with the ConversationHandler states.
    # It's generally better to handle unexpected messages within conversation states if needed.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    application.run_polling()
