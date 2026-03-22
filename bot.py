import asyncio
import errno
import hashlib
import socket
import sys
import warnings

# Pyrogram calls asyncio.get_event_loop() while importing; Python 3.10+ may have no
# default loop on the main thread (Windows / 3.12+), which breaks Pyrogram import.
if sys.platform == "win32":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import plugins.monkey_patch
from pyrogram import Client, idle, __version__
from pyrogram.raw.all import layer
import time
from pyrogram.errors import FloodWait
from datetime import date, datetime
from pathlib import Path
import importlib.util
import pytz
from aiohttp import web
from database.ia_filterdb import Media, Media2
from database.users_chats_db import db
import info
from info import *
from utils import temp
from Script import script
from plugins import web_server, check_expired_premium, keep_alive
from dreamxbotz.Bot import dreamxbotz
from dreamxbotz.util.keepalive import ping_server
from dreamxbotz.Bot.clients import initialize_clients
from PIL import Image
Image.MAX_IMAGE_PIXELS = 500_000_000

import logging
import logging.config

logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("aiohttp.web").setLevel(logging.ERROR)
logging.getLogger("pymongo").setLevel(logging.WARNING)

botStartTime = time.time()

_instance_lock_socket = None


def acquire_single_instance_lock():
    """One process per BOT_TOKEN. A second run would answer every update twice."""
    global _instance_lock_socket
    from info import BOT_TOKEN

    if not BOT_TOKEN:
        return
    h = int(hashlib.sha256(str(BOT_TOKEN).encode()).hexdigest()[:8], 16)
    lock_port = 31000 + (h % 2000)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", lock_port))
        sock.listen(1)
    except OSError:
        logging.error(
            "Another instance of this bot is already running (lock port %s). "
            "Stop the other python.exe or terminal — running twice causes duplicate messages and delays.",
            lock_port,
        )
        sys.exit(1)
    _instance_lock_socket = sock

def dreamxbotz_plugins_handler(app, plugins_dir: str | Path = "plugins", package_name: str = "plugins") -> list[str]:
    plugins_dir = Path(plugins_dir)
    loaded_plugins: list[str] = []

    if not plugins_dir.exists():
        logging.warning("Plugins Directory '%s' Does Not Exist.", plugins_dir)
        return loaded_plugins

    for file in sorted(plugins_dir.rglob("*.py")):
        if file.name == "__init__.py":
            continue

        rel_path = file.relative_to(plugins_dir).with_suffix("")
        import_path = package_name + ".".join([""] + list(rel_path.parts))

        try:
            spec = importlib.util.spec_from_file_location(import_path, file)
            if spec is None or spec.loader is None:
                logging.warning("Skipping %s (No Spec/Loader).", file)
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules[import_path] = module
            loaded_plugins.append(import_path)

            short_name = import_path.removeprefix(f"{package_name}.")
            logging.info("Loaded plugin: %s", short_name)

        except Exception:
            logging.exception("Failed To Import Plugin: %s", import_path)

    disp = getattr(app, "dispatcher", None)
    if disp is None:
        logging.warning("App Has No Dispatcher; Skipping Handler Regroup.")
        return loaded_plugins

    if 0 in disp.groups:
        all_handlers = list(disp.groups[0])
        for i, handler in enumerate(all_handlers):
            disp.remove_handler(handler, group=0)
            disp.add_handler(handler, group=i)
    else:
        logging.info("No Handlers In Group 0; Nothing To Regroup.")

    return loaded_plugins

async def dreamxbotz_start():
    print('\n\nInitalizing DreamxBotz')
    await dreamxbotz.start()
    bot_info = await dreamxbotz.get_me()
    dreamxbotz.username = bot_info.username
    await initialize_clients()
    loaded_plugins = dreamxbotz_plugins_handler(dreamxbotz)
    if loaded_plugins:
        logging.info("✅ Plugins Loaded: %d", len(loaded_plugins))
    else:
        logging.info("⚠️ No Plugins Loaded.")
    if ON_HEROKU:
        asyncio.create_task(ping_server()) 
    b_users, b_chats = await db.get_banned()
    temp.BANNED_USERS = b_users
    temp.BANNED_CHATS = b_chats
    await Media.ensure_indexes()
    if MULTIPLE_DB:
        await Media2.ensure_indexes()
        print("Multiple Database Mode On. Now Files Will Be Save In Second DB If First DB Is Full")
    else:
        print("Single DB Mode On ! Files Will Be Save In First Database")
    me = await dreamxbotz.get_me()
    temp.ME = me.id
    temp.U_NAME = me.username
    temp.B_NAME = me.first_name
    temp.B_LINK = me.mention
    dreamxbotz.username = '@' + me.username
    dreamxbotz.loop.create_task(check_expired_premium(dreamxbotz))
    logging.info(f"{me.first_name} with Pyrogram v{__version__} (Layer {layer}) started on {me.username}.")
    logging.info(LOG_STR)
    logging.info(script.LOGO)
    tz = pytz.timezone('Asia/Kolkata')
    today = date.today()
    now = datetime.now(tz)
    time = now.strftime("%H:%M:%S %p")
    await dreamxbotz.send_message(chat_id=LOG_CHANNEL, text=script.RESTART_TXT.format(temp.B_LINK, today, time))
    app = web.AppRunner(await web_server())
    await app.setup()
    bind_address = "0.0.0.0"
    listen_port = PORT
    port_busy = {errno.EADDRINUSE, 10048}
    for candidate in range(PORT, PORT + 64):
        site = web.TCPSite(app, bind_address, candidate)
        try:
            await site.start()
            listen_port = candidate
            break
        except OSError as e:
            if e.errno in port_busy or getattr(e, "winerror", None) == 10048:
                if candidate == PORT:
                    logging.warning(
                        "Port %s is already in use (another bot instance or app). "
                        "Trying the next free port…",
                        PORT,
                    )
                continue
            raise
    else:
        raise OSError(
            f"Could not bind web server: ports {PORT}–{PORT + 63} are all in use. "
            "Stop the other process or set PORT in .env to a free port."
        )
    if listen_port != PORT:
        info.PORT = listen_port
        logging.warning(
            "Web server listening on port %s (PORT in .env was %s). "
            "Point your tunnel / reverse proxy at this port if you use streaming.",
            listen_port,
            PORT,
        )
    dreamxbotz.loop.create_task(keep_alive())
    await idle()
    
if __name__ == '__main__':
    acquire_single_instance_lock()
    loop = asyncio.get_event_loop()
    while True:
        try:
            loop.run_until_complete(dreamxbotz_start())
            break  
        except FloodWait as e:
            print(f"FloodWait! Sleeping for {e.value} seconds.")
            time.sleep(e.value) 
        except KeyboardInterrupt:
            logging.info('Service Stopped Bye 👋')
            break
