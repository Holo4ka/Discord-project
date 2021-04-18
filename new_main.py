import discord
import youtube_dl
from discord.ext import commands
import asyncio
import requests
from data import db_session
from data.user import User
import datetime


intents = discord.Intents.all()
bot = commands.Bot(command_prefix='~', intents=intents)
TOKEN = 'token'

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
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
queue = asyncio.Queue()
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


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, discord.ext.commands.errors.DiscordException):
        await ctx.send("Something has gone wrong.")


@bot.command(name='play', pass_context=True)
async def play(ctx, *url):
    # try:
    global player
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
    await queue.put(url)
    await ctx.message.channel.send('Добавлено в очередь:\n' + url)
    while not queue.empty():
        if not player.is_playing():
            url = await queue.get()
            with youtube_dl.YoutubeDL(ytdl_format_options) as ydl:
                song_info = ydl.extract_info(url, download=False)
            ctx.message.guild.voice_client.play(
                discord.FFmpegPCMAudio(song_info["formats"][0]["url"]))
            ctx.message.guild.voice_client.source = discord.PCMVolumeTransformer(ctx.message.guild.voice_client.source)
            ctx.message.guild.voice_client.source.volume = 1
            await ctx.message.channel.send('Сейчас играет:\n' + url)
        elif player.is_playing():
            await asyncio.sleep(1)
    # except UrlError:
    #     await ctx.message.channel.send('Некорректная ссылка')
    # except Exception as e:
    #     print(e)


@bot.command(pass_context=True, name='pause')
async def pause(ctx):
    if ctx.message.guild.voice_client.is_playing():
        ctx.message.guild.voice_client.pause()


@bot.command(pass_context=True, name='stop')
async def stop(ctx):
    global queue, player
    ctx.message.guild.voice_client.stop()
    await ctx.message.guild.voice_client.disconnect()
    queue = asyncio.Queue()
    await ctx.message.channel.send('Проигрывание завершено')
    player = None


@bot.command(pass_context=True, name='resume')
async def resume(ctx):
    if ctx.message.guild.voice_client.is_paused():
        ctx.message.guild.voice_client.resume()


@bot.command(pass_context=True, name='leave')
async def leave(ctx):
    author_channel = ctx.message.author.voice.voice_channel
    await author_channel.disconnect()


@bot.command(name='give_role')
async def giverole(ctx, user: discord.Member, role: discord.Role):
    await user.add_roles(role)
    await ctx.send(f"Хей, пользователю {user.name} была выдана роль {role.name}!")


@bot.command(name='create_role')
async def createrole(ctx, role_name, color=discord.Colour(0)):
    guild = ctx.guild
    await guild.create_role(name=role_name, color=color)
    await ctx.send(f'Роль {role_name} создалась!')


@bot.command(name='delete_role')
async def deleterole(ctx, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if role:
        await role.delete()
        await ctx.send(f"Роль {role_name} удалена!")
    else:
        await ctx.send("Такой роли не существует!")


bot.run(TOKEN)
