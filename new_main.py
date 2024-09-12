import discord
from discord.ext import commands
import asyncio
import requests
from data import db_session
from data.user import User
import os
import datetime
import logging
import yt_dlp
from yandex_music import ClientAsync, Track
import pafy


TOKEN = ''
YOUTUBE_TOKEN = ''  # Токен скрыт в целях безопасности
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='~', intents=intents, help_command=None)
isses = {}
loop = asyncio.get_event_loop()

YANDEX_TOKEN = ''  # Токен скрыт в целях безопасности
# yandex_client = loop.run_until_complete(ClientAsync(YANDEX_TOKEN).init())


ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '',
    'restrictfilenames': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes  --verbose
}

FFMPEG_OPTIONS = {

    'options': '-vn'
}

# logging.basicConfig(filename='logs.txt', level=0)
players = {}
player = None
db_session.global_init('db/discord_users.db')
db_sess = db_session.create_session()
administration_roles = {}
servers = {}
voices = {}
queues = {}
titles = {}


class UrlError(Exception):
    pass


def set_queues():
    for id in servers.keys():
        queues[id] = asyncio.Queue(maxsize=1000)


def youtube_url(string: str):
    protocol = string.startswith('https://') or string.startswith('http://')
    address = 'youtube.com' in string
    params = 'watch?v=' in string
    return protocol and address and params


def youtube_shorter_url(string: str):
    protocol = string.startswith('https://') or string.startswith('http://')
    address = 'youtu.be' in string
    return protocol and address


def yandex_url(string: str):
    protocol = string.startswith('https://') or string.startswith('http://')
    address = 'music.yandex.ru' in string
    params = 'album' in string and 'track' in string
    return protocol and address and params


def any_url(string: str):
    return string.startswith('https://') or string.startswith('http://')


def check_roles(ctx):
    author = ctx.message.author
    administrator = False
    for role in administration_roles[ctx.message.guild.id]:
        for adm_role in author.roles:
            if role == adm_role.name:
                administrator = True
                break
    return administrator


def same_voice(ctx):
    global player
    author_ch = ctx.message.author.voice.channel
    a = set(voices.keys())
    current_ch = None if ctx.message.guild.id not in voices.keys() else voices[ctx.message.guild.id]
    return author_ch == current_ch or current_ch is None


def set_admin_roles(guild):
    administration_roles = []
    for role in guild.roles:
        if role.permissions.administrator:
            administration_roles.append(role.name)
        elif role.name == '@everyone':
            everyone = role
    if not administration_roles:
        for j in range(len(guild.roles)):
            if guild.roles[j].name == 'Yandex Lyceum Bot':
                administration_roles.extend(guild.roles[j + 1:])
    if not administration_roles or (len(administration_roles) == 1 and administration_roles[0] == 'Yandex Lyceum Bot'):
        administration_roles.append(everyone.name)
    return administration_roles


@bot.event
async def on_ready():
    global db_sess, servers
    print(f'{bot.user} подключен к Discord!')
    for guild in bot.guilds:
        print(
            f'{bot.user} подключились к чату:\n'
            f'{guild.name}(id: {guild.id})\n'
        )
        servers[guild.id] = None
        isses[guild.id] = 0
        titles[guild.id] = ''
        users_id = [int(user.user_id) for user in db_sess.query(User).all()]
        for elem in guild.members:
            if elem.id in users_id:
                continue
            user = User()
            user.user_id = int(elem.id)
            user.join_date = elem.joined_at
            db_sess.add(user)
            db_sess.commit()
        administration_roles[guild.id] = set_admin_roles(guild)
        set_queues()
    print('Готов к работе')


@bot.event
async def on_member_join(member: discord.Member):
    global db_sess
    user = User()
    user.user_id = member.id
    user.join_date = datetime.datetime.now()
    db_sess.add(user)
    db_sess.commit()
    for guild in bot.guilds:
        for channel in guild.channels:
            if channel.id == 407923847602503684:
                await channel.send(f'Приветствуем, <@{member.id}>!')
                return


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send('Проверьте, все ли нужные данные для команды вы написали.')
    elif isinstance(error, commands.errors.BadArgument):
        await ctx.send('Проверьте корректность написания данных для команды.')
    elif isinstance(error, commands.errors.CommandInvokeError):
        await ctx.send('Скорее всего, у меня нет прав на эту команду.')
    elif isinstance(error, commands.errors.DiscordException):
        await ctx.send('Что-то пошло не так!')


@bot.command(name="test")
async def nplay(ctx, *url):
    global player
    if player is None:
        author_channel = ctx.message.author.voice.channel
        voices[ctx.message.guild.id] = author_channel
        await author_channel.connect()
        servers[ctx.message.guild.id] = player = ctx.message.guild.voice_client
    song = pafy.new(url[0])
    audio = song.getbestaudio()
    source = discord.FFmpegPCMAudio(audio.url, **FFMPEG_OPTIONS)
    ctx.message.guild.voice_client.play(source)


async def play(ctx, id):
    try:
        for _ in range(queues[id].maxsize):
            getting = queues[id].get_nowait()
            duration, titles[id], current = getting
            ctx.message.guild.voice_client.play(
                discord.FFmpegPCMAudio(f'{current}_{ctx.message.guild.id}.mp3', executable='ffmpeg.exe'))
            await ctx.message.channel.send('Сейчас играет:\n' + '`' + titles[id] + '`')
            await asyncio.sleep(duration + 2)
    except asyncio.QueueEmpty:
        return


@bot.command(name='play')
async def add_to_queue(ctx, *url):
    global player, isses
    try:
        if not same_voice(ctx):
            return
        if len(url) == 0:
            return
        elif len(url) != 1:
            url = ' '.join(url)
            parts = '%20'.join(url.split())
            res = requests.get(
                f'https://youtube.googleapis.com/youtube/v3/search?part=snippet&maxResults=25&q={parts}&key={YOUTUBE_TOKEN}').json()
            id = res['items'][0]['id']['videoId']
            url = f'https://www.youtube.com/watch?v={id}'
            way = 'youtube'
        elif youtube_url(url[0]):
            url = url[0]
            way = 'youtube'
        elif youtube_shorter_url(url[0]):
            id = url[0].split('/')[-1].split('?')[0]
            url = f'https://www.youtube.com/watch?v={id}'
            way = 'youtube'
        elif yandex_url(url[0]):
            way = 'yandex'
            url = url[0]
        elif len(url) == 1 and not any_url(url[0]):
            search = url[0]
            res = requests.get(
                f'https://youtube.googleapis.com/youtube/v3/search?part=snippet&maxResults=25&q={search}&key={YOUTUBE_TOKEN}').json()
            id = res['items'][0]['id']['videoId']
            url = f'https://www.youtube.com/watch?v={id}'
            way = 'youtube'
        elif len(url) == 1 and not youtube_url(url[0]) and not yandex_url(url[0]):
            raise UrlError
        player = servers[ctx.message.guild.id]
        if player is None:
            author_channel = ctx.message.author.voice.channel
            voices[ctx.message.guild.id] = author_channel
            await author_channel.connect()
            servers[ctx.message.guild.id] = player = ctx.message.guild.voice_client
        await ctx.message.channel.send('Добавлено в очередь:\n' + '`' + url + '`')
        if way == 'youtube':
            ydl_opts = {
                'format': 'bestaudio/best',  # берем самое лучшее качество видео и фото
                'outtmpl': f'{isses[ctx.message.guild.id]}_{str(ctx.message.guild.id)}.mp3',  # Имя файла
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                song_info = ydl.extract_info(url, download=False)
                ydl.download(url)
                to_put = (int(song_info['duration']), song_info['title'], isses[ctx.message.guild.id])
        elif way == 'yandex':
            parts = url.split('/')
            alb = parts[4]
            num = parts[6]
            yandex_client = []
            track_list = await yandex_client.tracks([f'{num}:{alb}'])
            filename = f'{isses[ctx.message.guild.id]}_{str(ctx.message.guild.id)}.mp3'
            track = track_list[0]
            await track.download_async(filename=f"E:\Яндекс.Лицей\Discord-project\\{filename}")
            duration = track.duration_ms
            title = track.title
            to_put = (int(duration), title, isses[ctx.message.guild.id])
        queues[ctx.message.guild.id].put_nowait(to_put)
        isses[ctx.message.guild.id] += 1
        if not player.is_playing():
            await play(ctx=ctx, id=ctx.message.guild.id)
    except UrlError:
        await ctx.message.channel.send('Неправильный URL.')


@bot.command(pass_context=True, name='move')
async def move(ctx):
    global player
    voice_members = voices[ctx.message.guild.id].members
    if len(voice_members) == 1:
        new_channel = ctx.message.author.voice.channel
        await ctx.message.guild.voice_client.move_to(new_channel)
        voices[ctx.message.guild.id] = new_channel
        await skip(ctx)
        await ctx.message.channel.send('Меняю канал')
    else:
        await ctx.message.channel.send('Я не могу поменять канал, так как у меня уже есть слушатели')
        return


@bot.command(pass_context=True, name='stop')
async def stop(ctx):
    global queue, player, isses
    ctx.message.guild.voice_client.stop()
    await ctx.message.guild.voice_client.disconnect()
    queues[ctx.message.guild.id] = asyncio.Queue(maxsize=1000)
    await ctx.message.channel.send('Проигрывание завершено')
    servers[ctx.message.guild.id] = None
    for a in range(isses[ctx.message.guild.id]):
        os.remove(f'{a}_{ctx.message.guild.id}.mp3')
    isses[ctx.message.guild.id] = 0


@bot.command(pass_context=True, name='skip')
async def skip(ctx):
    global queue, player
    ctx.message.guild.voice_client.stop()
    if not queues[ctx.message.guild.id].empty():
        await ctx.message.channel.send('Трек пропущен')
        print(player.is_playing())
        await play(ctx=ctx, id=ctx.message.guild.id)


@bot.command(pass_context=True, name='pause')
async def pause(ctx):
    if ctx.message.guild.voice_client.is_playing():
        ctx.message.guild.voice_client.pause()
        await ctx.message.channel.send('Поставлено на паузу')


@bot.command(pass_context=True, name='resume')
async def resume(ctx):
    if ctx.message.guild.voice_client.is_paused():
        ctx.message.guild.voice_client.resume()
        await ctx.message.channel.send('Продолжение проигрывания')


@bot.command(name='queue')
async def show_queue(ctx):
    channel = ctx.message.channel
    strings = []
    now = f'{titles[ctx.message.guild.id]} (играет сейчас)'
    for i in range(queues[ctx.message.guild.id].qsize()):
        url = await queues[ctx.message.guild.id].get()
        await queues[ctx.message.guild.id].put(url)
        strings.append(f'{i + 2} - {url[1]}')
    output = "\n".join(strings)
    msg = f'''Очередь воспроизведения:
`1 -  {now}
 {output}`'''
    await channel.send(msg)


@bot.command(name='ban')
async def ban(ctx, user: discord.Member, reason=None):
    if check_roles(ctx):
        server = ctx.guild
        await server.ban(user, reason=reason)
        msg = f'{user.name} был забанен.'
        if reason:
            msg += f' Причина: {reason}.'
        await ctx.send(msg)
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='unban')
async def unban(ctx, user, reason=None):
    if check_roles(ctx):
        server = ctx.guild
        banned_users = await server.bans()
        user_found = False
        for ban_entry in banned_users:
            member = ban_entry.user
            if member.name == user:
                unban_user = member
                user_found = True
        if not user_found:
            await ctx.send('Пользователь не найден.')
            return
        await server.unban(unban_user)
        msg = f'{unban_user.name} был разбанен.'
        if reason:
            msg += f' Причина: {reason}.'
        await ctx.send(msg)
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='kick')
async def kick(ctx, user: discord.Member, reason=None):
    if check_roles(ctx):
        server = ctx.guild
        await server.kick(user, reason=reason)
        msg = f'{user.name} был кикнут.'
        if reason:
            msg += f' Причина: {reason}.'
        await ctx.send(msg)
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='mute')
async def mute(ctx, user: discord.Member, reason=None):
    if check_roles(ctx):
        mute_role = discord.utils.get(ctx.guild.roles, name='MUTED')
        await user.add_roles(mute_role)
        msg = f'{user.name} был замучен.'
        if reason:
            msg += f' Причина: {reason}.'
        await ctx.send(msg)
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='unmute')
async def unmute(ctx, user: discord.Member):
    if check_roles(ctx):
        mute_role = discord.utils.get(ctx.guild.roles, name='MUTED')
        u_roles = user.roles
        if mute_role not in u_roles:
            await ctx.send(f'Пользователь {user.name} не был замучен.')
            return
        await user.remove_roles(mute_role)
        await ctx.send(f'{user.name} был размучен.')
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='add_administrator_role')
async def add_administrator_role(ctx, role: discord.Role):
    global administration_roles
    if check_roles(ctx):
        administration_roles[ctx.message.guild.id].insert(0, role.name)
        await ctx.message.channel.send(f'Роль была добавлена к списку администраторских')
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='del_administrator_role')
async def del_administrator_role(ctx, role: discord.Role):
    global administration_roles
    author = ctx.message.author
    role_index = administration_roles[ctx.message.guild.id].index(author.roles[-1].name)
    del_role_index = administration_roles[ctx.message.guild.id].index(role.name)
    if check_roles(ctx) and role_index > del_role_index:
        del administration_roles[ctx.message.guild.id][del_role_index]
        await ctx.message.channel.send(f'Роль {role} больше не является администраторской')
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='check_administrator_roles')
async def check_adm_roles(ctx):
    author = ctx.message.author
    if check_roles(ctx):
        roles_list = []
        for role in administration_roles[ctx.message.guild.id]:
            roles_list.append(role)
        output = '\n'.join(roles_list)
        await ctx.message.channel.send(f'''Список администраторских ролей для этого сервера:
{output}''')


@bot.command(name='change_nick')
async def changenick(ctx, user: discord.Member, *nick):
    if check_roles(ctx):
        nick = ' '.join(nick)
        await user.edit(nick=nick)
        await ctx.send(f'Никнейм пользователя {user.name} был изменён на {user.nick}')
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='give_roles')
async def giveroles(ctx, user: discord.Member, *roles: discord.Role):
    if check_roles(ctx):
        if not roles:
            await ctx.send('Должна быть написана хотя бы одна роль.')
            return
        await user.add_roles(*roles)
        if len(roles) == 1:
            await ctx.send(f"Пользователю {user.name} была выдана роль {roles[0].name}!")
        else:
            roles_str = ', '.join(r.name for r in roles)
            await ctx.send(f"Пользователю {user.name} были выданы роли: {roles_str}.")
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='take_roles')
async def takeroles(ctx, user: discord.Member, *roles: discord.Role):
    if check_roles(ctx):
        if not roles:
            await ctx.send('Должна быть написана хотя бы одна роль.')
        u_roles = user.roles
        for r in roles:
            if r not in u_roles:
                await ctx.send(f'У пользователя {user.name} нет роли {r.name}.')
                return
        await user.remove_roles(*roles)
        if len(roles) == 1:
            await ctx.send(f"У пользователя {user.name} была отнята роль {roles[0].name}!")
        else:
            roles_str = ', '.join(r.name for r in roles)
            await ctx.send(f"У пользователя {user.name} были отняты роли: {roles_str}.")
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='create_role')
async def createrole(ctx, role_name, color=discord.Colour(0)):
    if check_roles(ctx):
        guild = ctx.guild
        await guild.create_role(name=role_name, color=color)
        await ctx.send(f'Роль {role_name} создалась!')
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='edit_role_color')
async def editrolecolor(ctx, role: discord.Role, color: discord.Colour):
    if check_roles(ctx):
        await role.edit(color=color)
        await ctx.send(f'Цвет роли {role.name} был изменён на {role.color}(hex).')
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='edit_role_name')
async def editrolename(ctx, role: discord.Role, *name):
    if check_roles(ctx):
        prev_name = role.name
        name_now = ' '.join(name)
        await role.edit(name=name_now)
        await ctx.send(f'Имя роли {prev_name} было изменено на {role.name}.')
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='delete_role')
async def deleterole(ctx, role: discord.Role):
    if check_roles(ctx):
        await ctx.send(f"Роль {role.name} удалена!")
        await role.delete()
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='statistic')
async def show_statistic(ctx):
    author = db_sess.query(User).filter(User.user_id == ctx.message.author.id)[0]
    days = str(datetime.datetime.now() - author.join_date).split()[0]
    roles = ctx.message.author.roles
    output_roles = ''
    for b in range(len(roles)):
        if b == 0:
            continue
        output_roles = output_roles + f'@{roles[b].name}\n'
    msg = f'''`Статистика для пользователя: {ctx.message.author}
Присоединился к серверу: {author.join_date.date()} ({days} дней)
Роли:
{output_roles}`'''
    await ctx.send(msg)


@bot.command(name='help')
async def help(ctx, *section):
    channel = ctx.message.channel
    if len(section) == 0:
        msg = f'''Префикс бота - ~
Категории (Напишите `~help категория`, чтобы получить список команд):
• music
• roles
• users
• administration'''
    else:
        category = section[0].lower()
        if category == 'music':
            msg = '''Список команд для категории Music:
play [запрос или ссылка на видео youtube] - начать проигрывание песни (или добавить ее в очередь)
stop - останавливает проигрывание и очищает очередь
skip - пропуск текущего трека
pause - поставить трек на паузу
resume - продолжить проигрывание
queue - показывает текущую очередь воспроизведения'''
        elif category == 'roles':
            msg = '''Список команд для категории Roles:
give_roles [пользователь] [роль или несколько ролей] - выдает пользователю указанные роли (если имеются права на это)
take_roles [пользователь] [роль или несколько ролей] - забирает у пользователя указанные роли (если имеются права на это)
create_roles [название] [цвет в формате hex или само название] - создает роль заданного цвета без прав
edit_role_color [роль] [цвет в формате hex или само название] - изменяет цвет роли (если имеются права на это)
edit_role_name [роль] [новое название] - изменяет имя роли (если имеются права на это)
delete_role [роль] - удаляет роль (если имеются права на это)
Примечание: для использования ролей необходимо иметь роль администратора'''
        elif category == 'users':
            msg = '''Список команд для категории Users:
change_nick [пользователь] [новый ник] - меняет ник указанного пользователя (необходимо иметь роль администратора)
statistic - показывает вашу статистику'''
        elif category == 'administration':
            msg = '''Список команд для категории Administration:
mute [пользователь] [причина (необязательно)] - мутит указанного пользователя
unmute [пользователь] [причина (необязательно)] - снимает мут с указанного пользователя
kick [пользователь] [причина (необязательно)] - кикает указанного пользователя
ban [пользователь] [причина (необязательно)] - банит указанного пользователя
unban [пользователь] [причина (необязательно)] - снимает бан с указанного пользователя
add_administrator_role [уже существующая роль] - добавляет роль в список администраторских
del_administrator_role [уже существующая роль] - удаляет роль из списка администраторских
check_administrator_roles - вывод списка администраторских ролей
Примечания: 
1. Для использования этих команд вам необходимо иметь роль администратора
2. При перезапуске бота придется заново назначать роли администратора'''
        else:
            msg = 'Я не знаю такой категории'
    await channel.send(msg)


@bot.command(name='alert')
@commands.has_permissions(administrator=True)
async def say_alert(ctx, *msg):
    msg = ' '.join(msg)
    guild = ctx.message.guild
    if guild.id == 407923846654459917:
        for guild in bot.guilds:
            for category in guild.channels:
                for channel in category.channels:
                    await channel.send(msg)
                    break
                break


@bot.command(name='die')
@commands.has_permissions(administrator=True)
async def die(ctx):
    global player
    if player:
        if player.is_playing():
            await stop(ctx)
    for guild in bot.guilds:
        for channel in guild.channels:
            if channel.id == 522053860710416394:
                await channel.send('Бот отключается')
    print('\nПрекращение работы бота')
    await bot.close()


bot.run(TOKEN)
