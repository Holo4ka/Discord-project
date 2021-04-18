import discord
import youtube_dl
from discord.ext import commands
import asyncio

TOKEN = 'token'
bot = commands.Bot(command_prefix='~')

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
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


# Класс для превращения ссылки в объект, который может проиграть discord-бот
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # Взять первый объект
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


@bot.event
async def on_ready():
    print(f'{bot.user} подключен к Discord!')
    for guild in bot.guilds:
        print(
            f'{bot.user} подключились к чату:\n'
            f'{guild.name}(id: {guild.id})\n'
        )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, discord.ext.commands.errors.DiscordException):
        await ctx.send("Something has gone wrong.")


@bot.command(name='play', pass_context=True)
async def play(ctx, url):
    author_channel = ctx.message.author.voice.channel
    await author_channel.connect()
    # # server = ctx.message.server
    # player = author_channel.create_ytdl_player(url)
    # # players[server.id] = player
    # player.start()
    with youtube_dl.YoutubeDL(ytdl_format_options) as ydl:
        song_info = ydl.extract_info(url, download=False)
    ctx.message.guild.voice_client.play(
        discord.FFmpegPCMAudio(song_info["formats"][0]["url"], executable='ffmpeg/bin/ffmpeg.exe'))
    ctx.message.guild.voice_client.source = discord.PCMVolumeTransformer(ctx.message.guild.voice_client.source)
    ctx.message.guild.voice_client.source.volume = 1


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
