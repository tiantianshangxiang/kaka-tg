# -*- coding: utf-8 -*-
"""Telethon Session String 生成脚本（本地运行一次）。

为什么需要它：
    Telethon 的 User Session 在 Docker 里无法交互式扫码/收验证码登录。最佳实践是
    在本地电脑跑一次本脚本，登录成功后把打印出的 **Session String** 复制到插件
    配置项 "TG Session String" 里，容器内即可免交互使用。

使用方法：
    1. 本地安装： pip install telethon
    2. 到 https://my.telegram.org 申请 api_id / api_hash
    3. 运行：    python gen_tg_session.py
    4. 按提示输入 api_id / api_hash / 手机号 / 登录验证码（如开了两步验证还要密码）
    5. 复制控制台打印的 "1" 开头长字符串到插件配置

注意：
    - 该脚本不会保存任何信息到磁盘，Session String 仅打印一次，请妥善保管。
    - 用你的 Telegram 账号登录，且该账号需已加入目标频道，才能读取其历史消息。
"""
import asyncio
import sys


async def main():
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("请先安装 telethon： pip install telethon")
        sys.exit(1)

    api_id = input("请输入 api_id: ").strip()
    api_hash = input("请输入 api_hash: ").strip()
    if not api_id or not api_hash:
        print("api_id / api_hash 不能为空")
        sys.exit(1)

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.start()
    if not await client.is_user_authorized():
        print("登录失败，请检查验证码/两步验证密码")
        sys.exit(1)

    session_string = StringSession.save(client.session)
    print("\n========== 复制下面这一整行到插件配置 TG Session String ==========")
    print(session_string)
    print("==================================================================\n")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
