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


# @bot.event
# async def on_command_error(ctx, error):
#     if isinstance(error, commands.errors.MissingRequiredArgument):
#         await ctx.send('Проверьте, все ли нужные данные для команды вы написали.')
#     elif isinstance(error, commands.errors.BadArgument):
#         await ctx.send('Проверьте корректность написания данных для команды.')
#     elif isinstance(error, commands.errors.CommandInvokeError):
#         await ctx.send('Скорее всего, у меня нет прав на эту команду.')
#     elif isinstance(error, UrlError):
#         await ctx.send('Неправильный URL.')
#     elif isinstance(error, commands.errors.DiscordException):
#         await ctx.send('Что-то пошло не так!')


@bot.command(name='ban')
async def ban(ctx, user: discord.Member, reason=None):
    server = ctx.guild
    await server.ban(user, reason=reason)
    msg = f'{user.name} был забанен.'
    if reason:
        msg += f' Причина: {reason}.'
    await ctx.send(msg)


@bot.command(name='unban')
async def unban(ctx, user, reason=None):
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


@bot.command(name='kick')
async def kick(ctx, user: discord.Member, reason=None):
    server = ctx.guild
    await server.kick(user, reason=reason)
    msg = f'{user.name} был кикнут.'
    if reason:
        msg += f' Причина: {reason}.'
    await ctx.send(msg)


@bot.command(name='mute')
async def mute(ctx, user: discord.Member, reason=None):
    mute_role = discord.utils.get(ctx.guild.roles, name='MUTED')
    await user.add_roles(mute_role)
    msg = f'{user.name} был замучен.'
    if reason:
        msg += f' Причина: {reason}.'
    await ctx.send(msg)


@bot.command(name='unmute')
async def unmute(ctx, user: discord.Member):
    mute_role = discord.utils.get(ctx.guild.roles, name='MUTED')
    u_roles = user.roles
    if mute_role not in u_roles:
        await ctx.send(f'Пользователь {user.name} не был замучен.')
        return
    await user.remove_roles(mute_role)
    await ctx.send(f'{user.name} был размучен.')


@bot.command(name='warn', pass_context=True)
async def warn(ctx, user: discord.User, reason=None):
    # user = db_sess.query(User).filter(User.user_id == user.id)[0]
    # user.warn()
    # db_sess.commit()
    msg = f'Пользователь {user.name} получил предупреждение.'
    if reason:
        msg += f' Причина: {reason}.'
    await ctx.send(msg)


@bot.command(name='change_nick')
async def changenick(ctx, user: discord.Member, *nick):
    nick = ' '.join(nick)
    await user.edit(nick=nick)
    await ctx.send(f'Никнейм пользователя {user.name} был изменён на {user.nick}')


@bot.command(name='give_roles')
async def giveroles(ctx, user: discord.Member, *roles: discord.Role):
    if not roles:
        await ctx.send('Должна быть написана хотя бы одна роль.')
        return
    await user.add_roles(*roles)
    if len(roles) == 1:
        await ctx.send(f"Пользователю {user.name} была выдана роль {roles[0].name}!")
    else:
        roles_str = ', '.join(r.name for r in roles)
        await ctx.send(f"Пользователю {user.name} были выданы роли: {roles_str}.")


@bot.command(name='take_roles')
async def takeroles(ctx, user: discord.Member, *roles: discord.Role):
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
async def editrolename(ctx, role: discord.Role, *name):
    prev_name = role.name
    name_now = ' '.join(name)
    await role.edit(name=name_now)
    await ctx.send(f'Имя роли {prev_name} было изменено на {role.name}.')


@bot.command(name='delete_role')
async def deleterole(ctx, role: discord.Role):
    await ctx.send(f"Роль {role.name} удалена!")
    await role.delete()


bot.run(TOKEN)
