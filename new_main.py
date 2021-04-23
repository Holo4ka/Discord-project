import discord
from discord.ext import commands

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='~', intents=intents)


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
        await ctx.send(f"Хей, пользователю {user.name} была выдана роль {roles[0].name}!")
    else:
        roles_str = ', '.join(r.name for r in roles)
        await ctx.send(f"Хей, пользователю {user.name} были выданы роли: {roles_str}.")


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
        await ctx.send(f"Хей, у пользователя {user.name} была отнята роль {roles[0].name}!")
    else:
        roles_str = ', '.join(r.name for r in roles)
        await ctx.send(f"Хей, у пользователя {user.name} были отняты роли: {roles_str}.")


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
