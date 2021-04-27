import discord
import youtube_dl
from discord.ext import commands
import asyncio
import requests
from data import db_session
from data.user import User
import os
import datetime
import logging


intents = discord.Intents.all()
bot = commands.Bot(command_prefix='~', intents=intents, help_command=None)
i = 0

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '',
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
logging.basicConfig(filename='logs.txt', level=20)
players = {}
queue = asyncio.Queue(maxsize=1000)
player = None
db_session.global_init('db/discord_users.db')
db_sess = db_session.create_session()
title = None
administration_roles = []


class UrlError(Exception):
    pass


def is_url(string: str):
    protocol = string.startswith('https://') or string.startswith('http://')
    address = 'youtube.com' in string
    params = 'watch?v=' in string
    return protocol and address and params


def check_roles(ctx):
    author = ctx.message.author
    administrator = False
    for role in administration_roles:
        if role in author.roles:
            administrator = True
            break
    return administrator


def set_admin_roles(guild):
    global administration_roles
    for role in guild.roles:
        if role.permissions.administrator:
            administration_roles.append(role)
        elif role.name == '@everyone':
            everyone = role
    if not administration_roles:
        for j in range(len(guild.roles)):
            if guild.roles[j].name == 'Yandex Lyceum Bot':
                administration_roles.extend(guild.roles[j + 1:])
    if not administration_roles:
        administration_roles.append(everyone)
    return administration_roles


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
            user.join_date = elem.joined_at
            db_sess.add(user)
            db_sess.commit()
        set_admin_roles(guild)
        print(administration_roles)


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


async def play(ctx):
    global title
    try:
        for _ in range(queue.maxsize):
            getting = queue.get_nowait()
            duration, title, current = getting
            ctx.message.guild.voice_client.play(
                discord.FFmpegPCMAudio(f'{current}.webm'))
            await ctx.message.channel.send('Сейчас играет:\n' + '`' + title + '`')
            await asyncio.sleep(duration + 2)
    except asyncio.QueueEmpty:
        return


@bot.command(name='play')
async def add_to_queue(ctx, *url):
    global player, i
    try:
        if len(url) == 0:
            return
        elif len(url) == 1 and not is_url(url[0]):
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
    except UrlError:
        await ctx.message.channel.send('Неправильный URL.')


@bot.command(pass_context=True, name='stop')
async def stop(ctx):
    global queue, player, i
    ctx.message.guild.voice_client.stop()
    await ctx.message.guild.voice_client.disconnect()
    queue = asyncio.Queue(maxsize=1000)
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


@bot.command(name='queue')
async def show_queue(ctx):
    global title
    channel = ctx.message.channel
    songs = ''
    now = f'{title} (играет сейчас)'
    for _ in range(queue.qsize()):
        url = await queue.get()
        songs = songs + url[1] + '\n'
        await queue.put(url)
    msg = f'''Очередь воспроизведения:
`{now}
{songs}`'''
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


@bot.command(name='warn', pass_context=True)
async def warn(ctx, member: discord.Member, reason=None):
    if check_roles(ctx):
        user = db_sess.query(User).filter(User.user_id == member.id)[0]
        user.warn()
        db_sess.commit()
        msg = f'Пользователь {member.name} получил предупреждение.'
        if reason:
            msg += f' Причина: {reason}.'
        await ctx.send(msg)
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='add_administrator_role')
async def add_administrator_role(ctx, role: discord.Role):
    global administration_roles
    if check_roles(ctx):
        administration_roles.insert(0, role)
        await ctx.message.channel.send(f'Роль была добавлена к списку администраторских')
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


@bot.command(name='del_administrator_role')
async def del_administrator_role(ctx, role: discord.Role):
    author = ctx.message.author
    role_index = administration_roles.index(author.roles[-1])
    del_role_index = administration_roles.index(role)
    if check_roles(ctx) and role_index > del_role_index:
        del administration_roles[del_role_index]
        await ctx.message.channel.send(f'Роль {role} больше не является администраторской')
    else:
        await ctx.message.channel.send('У вас нет прав на эту команду')


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
Количество предупреждений: {author.warns}
Роли:
{output_roles}`'''
    await ctx.send(msg)


@bot.command(name='help')
async def help(ctx, *section):
    channel = ctx.message.channel
    if len(section) == 0:
        msg = f'''Префикс бота - ~
Категории (Напишите `~help категория`, чтобы получить список команд):
music
roles
users
administration'''
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
warn [пользователь] [причина (необязательно)] - выдает предупреждение указанному пользователю
mute [пользователь] [причина (необязательно)] - мутит указанного пользователя
unmute [пользователь] [причина (необязательно)] - снимает мут с указанного пользователя
kick [пользователь] [причина (необязательно)] - кикает указанного пользователя
ban [пользователь] [причина (необязательно)] - банит указанного пользователя
unban [пользователь] [причина (необязательно)] - снимает бан с указанного пользователя
add_administrator_role [уже существующая роль] - добавляет роль в список администраторских
del_administrator_role [уже существующая роль] - удаляет роль из списка администраторских
Примечание: для использования этих команд вам необходимо иметь роль администратора'''
    await channel.send(msg)


bot.run(TOKEN)
