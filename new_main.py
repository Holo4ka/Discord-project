import discord
import youtube_dl
from discord.ext import commands
import asyncio
import requests
from data import db_session
from data.user import User
import os


YOUTUBE_TOKEN = 'AIzaSyBiF_oZJFMMHYabcICvUk0dJe5QB4yr-Cc'
TOKEN = 'ODI0MTY2OTg3NTQxNjQzMjk0.YFrbUg.rH3B5mKVs5CLJGR_iGdfVLBf940'
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='~', intents=intents)
LETTERS = ['_', '-', ' ']
i = 0

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(title)s.webm',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

players = {}
queue = asyncio.Queue(maxsize=100)
player = None
db_session.global_init('db/discord_users.db')
db_sess = db_session.create_session()


class UrlError(Exception):
    pass


def is_url(string: str):
    protocol = string.startswith('https://') or string.startswith('http://')
    address = 'youtube.com' in string
    params = 'watch?v=' in string
    return protocol and address and params


@bot.event
async def on_ready():
    global db_sess
    print(f'{bot.user} подключен к Discord!')
    for guild in bot.guilds:
        print(
            f'{bot.user} подключились к чату:\n'
            f'{guild.name}(id: {guild.id})\n'
        )
        users_id = [int(user.user_id) for user in db_sess.query(User).all()]
        for elem in guild.members:
            if elem.id in users_id:
                continue
            user = User()
            user.user_id = int(elem.id)
            db_sess.add(user)
            db_sess.commit()


@bot.event
async def on_member_join(member: discord.Member):
    global db_sess
    user = User()
    user.user_id = member.id
    db_sess.add(user)
    db_sess.commit()
    for guild in bot.guilds:
        for channel in guild.channels:
            if channel.id == 407923847602503684:
                await channel.send(f'Приветствуем, <@{member.id}>!')
                return


# @bot.event
# async def on_message(message: discord.Message):
#     global db_sess
#     if message.author == bot.user:
#         return
#     author_id = message.author.id
#     user = db_sess.query(User).filter(User.user_id == author_id)[0]
#     user.add_message()
#     db_sess.commit()

async def play(ctx):
    try:
        for _ in range(queue.maxsize):
            getting = queue.get_nowait()
            duration, title, current = getting
            ctx.message.guild.voice_client.play(
                discord.FFmpegPCMAudio(f'{current}.webm'))
            await ctx.message.channel.send('Сейчас играет:\n' + '`' + title + '`')
            await asyncio.sleep(duration + 2)
            os.remove(f'{current}.webm')
    except asyncio.QueueEmpty:
        return


@bot.command(name='play')
async def add_to_queue(ctx, *url):
    global player, i
    if len(url) == 0:
        return
    elif len(url) == 1 and not is_url(url[0]) and 'https://' in url[0]:
        raise UrlError
    elif len(url) != 1 or not is_url(url[0]):
        url = ' '.join(url)
        parts = '%20'.join(url.split())
        res = requests.get(
            f'https://youtube.googleapis.com/youtube/v3/search?part=snippet&maxResults=25&q={parts}&key={YOUTUBE_TOKEN}').json()
        id = res['items'][0]['id']['videoId']
        url = f'https://www.youtube.com/watch?v={id}'
    elif is_url(url[0]):
        url = url[0]
    if player is None:
        author_channel = ctx.message.author.voice.channel
        await author_channel.connect()
        player = ctx.message.guild.voice_client
    ytdl_format_options['outtmpl'] = f'{i}.webm'
    await ctx.message.channel.send('Добавлено в очередь:\n' + url)
    with youtube_dl.YoutubeDL(ytdl_format_options) as ydl:
        song_info = ydl.extract_info(url, download=True)
    to_put = (int(song_info['duration']), song_info['title'], i)
    queue.put_nowait(to_put)
    i += 1
    if not player.is_playing():
        await play(ctx=ctx)


@bot.command(pass_context=True, name='stop')
async def stop(ctx):
    global queue, player, i
    ctx.message.guild.voice_client.stop()
    await ctx.message.guild.voice_client.disconnect()
    queue = asyncio.Queue()
    await ctx.message.channel.send('Проигрывание завершено')
    player = None
    for a in range(i):
        os.remove(f'{a}.webm')
    i = 0


@bot.command(pass_context=True, name='skip')
async def skip(ctx):
    global queue, player
    ctx.message.guild.voice_client.stop()
    if not queue.empty():
        await ctx.message.channel.send('Трек пропущен')
        print(player.is_playing())
        await play(ctx=ctx)


@bot.command(pass_context=True, name='pause')
async def pause(ctx):
    if ctx.message.guild.voice_client.is_playing():
        ctx.message.guild.voice_client.pause()
        await ctx.message.channel.send('Поставлено на паузу')


@bot.command(pass_context=True, name='resume')
async def resume(ctx):
    if ctx.message.guild.voice_client.is_paused():
        ctx.message.guild.voice_client.resume()
        await ctx.message.channel.send('Продолжение проигрывания...')


@bot.command(name='ban')
async def ban(ctx, user, reason=None):
    server = ctx.message.guild
    await server.ban(user, reason=reason)
    await ctx.message.channel.send(f'{user.name} был забанен {ctx.message.author}')
    if reason is not None:
        await ctx.message.channel.send(f'Причина: {reason}')


@bot.command(name='kick')
async def kick(ctx, user, reason):
    server = ctx.message.guild
    await server.kick(user, reason=reason)


@bot.command(name='mute')
async def mute(ctx, user):
    await user.add_roles(507885681289461760)


@bot.command(name='give_role')
async def giverole(ctx, user: discord.Member, role: discord.Role):
    await user.add_roles(role)
    await ctx.send(f"Хей, пользователю {user.name} была выдана роль {role.name}!")


@bot.command(name='create_role')
async def createrole(ctx, role_name, color=discord.Colour(0)):
    guild = ctx.guild
    await guild.create_role(name=role_name, color=color)
    await ctx.send(f'Роль {role_name} создалась!')


@bot.command(name='edit_role_color')
async def editrolecolor(ctx, role: discord.Role, color: discord.Colour):
    await role.edit(color=color)
    await ctx.send(f'Цвет роли {role.name} был изменён на {role.color}(hex).')


@bot.command(name='edit_role_name')
async def editrolename(ctx, role: discord.Role, name):
    await ctx.send(f'Имя роли {role.name} было изменено на {name}.')
    await role.edit(name=name)


@bot.command(name='delete_role')
async def deleterole(ctx, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if role:
        await role.delete()
        await ctx.send(f"Роль {role_name} удалена!")
    else:
        await ctx.send("Такой роли не существует!")


@bot.command(name='warn', pass_context=True)
async def warn(ctx, user, reason):
    server = ctx.message.guild
    user = db_sess.query(User).filter(User.user_id == user.id)[0]
    user.warn()
    db_sess.commit()
    await ctx.send('Warn')
    print('test')


bot.run(TOKEN)
