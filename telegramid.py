import asyncio
from telegram import Bot
from telegram.error import InvalidToken
TOKEN = '8023866565:AAG_YId2GbV8QuemDxjT-yR3xFumpzQFqEQ'

async def main():
    try:
        bot = Bot(TOKEN)
        bot_info = await bot.get_me()
        print(f'Đã kết nối với bot: {bot_info.first_name} (@{bot_info.username})')
        updates = await bot.get_updates(timeout=10)
        if not updates:
            print('\nKhông tìm thấy tin nhắn mới nào.')
            print('Vui lòng thực hiện các bước sau:')
            print(f'1. Mở Telegram và tìm bot @{bot_info.username}')
            print("2. Nhấn 'Start' hoặc gửi một tin nhắn bất kỳ cho nó.")
            print('3. Chạy lại script này.')
            return
        print('\nTìm thấy các cuộc trò chuyện sau:')
        seen_chat_ids = set()
        for u in updates:
            if u.message and u.message.chat.id not in seen_chat_ids:
                chat = u.message.chat
                print(f'  - Chat ID: {chat.id}')
                if chat.type == 'private':
                    print(f'    Tên: {chat.first_name} {chat.last_name or ''}')
                else:
                    print(f'    Tên nhóm: {chat.title}')
                seen_chat_ids.add(chat.id)
    except InvalidToken:
        print('LỖI: Token không hợp lệ. Vui lòng kiểm tra lại TOKEN của bạn.')
    except Exception as e:
        print(f'Đã xảy ra lỗi: {e}')
if __name__ == '__main__':
    asyncio.run(main())