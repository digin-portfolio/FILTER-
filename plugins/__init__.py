from aiohttp import web
from .route import routes
from asyncio import sleep 
from datetime import datetime
from database.users_chats_db import db
from os import getenv
from urllib.parse import urlparse
import info
from info import LOG_CHANNEL, URL, PREMIUM_LOGS
import aiohttp
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

async def check_expired_premium(client):
    while 1:
        data = await db.get_expired(datetime.now())
        for user in data:
            user_id = user["id"]
            await db.remove_premium_access(user_id)
            try:
                user = await client.get_users(user_id)
                await client.send_message(
                    chat_id=user_id,
                    text=f"<b>ʜᴇʏ {user.mention},\n\n𝑌𝑜𝑢𝑟 𝑃𝑟𝑒𝑚𝑖𝑢𝑚 𝐴𝑐𝑐𝑒𝑠𝑠 𝐻𝑎𝑠 𝐸𝑥𝑝𝑖𝑟𝑒𝑑 𝑇ℎ𝑎𝑛𝑘 𝑌𝑜𝑢 𝐹𝑜𝑟 𝑈𝑠𝑖𝑛𝑔 𝑂𝑢𝑟 𝑆𝑒𝑟𝑣𝑖𝑐𝑒 😊. 𝐼𝑓 𝑌𝑜𝑢 𝑊𝑎𝑛𝑡 𝑇𝑜 𝑇𝑎𝑘𝑒 𝑃𝑟𝑒𝑚𝑖𝑢𝑚 𝐴𝑔𝑎𝑖𝑛, 𝑇ℎ𝑒𝑛 𝐶𝑙𝑖𝑐𝑘 𝑂𝑛 𝑇ℎ𝑒 /plan 𝐹𝑜𝑟 𝑇ℎ𝑒 𝐷𝑒𝑡𝑎𝑖𝑙𝑠 𝑂𝐹 𝑇ℎ𝑒 𝑃𝑙𝑎𝑛𝑠..\n\n\n<blockquote>आपका 𝑷𝒓𝒆𝒎𝒊𝒖𝒎 𝑨𝒄𝒄𝒆𝒔𝒔 समाप्त हो गया है हमारी सेवा का उपयोग करने के लिए धन्यवाद 😊। यदि आप फिर से 𝑷𝒓𝒆𝒎𝒊𝒖𝒎 लेना चाहते हैं, तो योजनाओं के विवरण के लिए /plan पर 𝑪𝒍𝒊𝒄𝒌 करें।</blockquote></b>"
                )
                await client.send_message(PREMIUM_LOGS, text=f"<b>#Premium_Expire\n\nUser name: {user.mention}\nUser id: <code>{user_id}</code>")
            except Exception as e:
                print(e)
            await sleep(0.5)
        await sleep(1)

def _keepalive_ping_url():
    """Use public URL when valid; localhost + bound PORT when FQDN is 0.0.0.0 (local dev)."""
    custom = getenv("KEEPALIVE_URL", "").strip()
    if custom:
        return custom
    host = urlparse(URL).hostname
    if host in ("0.0.0.0", None, ""):
        port = getattr(info, "PORT", 8080)
        return f"http://127.0.0.1:{port}/"
    return URL


async def keep_alive():
    """Keep bot alive by sending periodic pings (Heroku-style; harmless if skipped locally)."""
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(298)
            ping = _keepalive_ping_url()
            try:
                async with session.get(ping) as resp:
                    if resp.status != 200:
                        logging.warning("Ping non-200 status: %s (%s)", resp.status, ping)
            except Exception as e:
                logging.error("Ping failed (%s): %s", ping, e)

