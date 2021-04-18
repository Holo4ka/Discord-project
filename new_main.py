import discord
import youtube_dl
from discord.ext import commands
import asyncio
import requests


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
queue = asyncio.Queue()
player = None


class UrlError(Exception):
    pass


def is_url(string: str):
    protocol = string.startswith('https://') or string.startswith('http://')
    address = 'youtube.com' in string
    params = 'watch?v=' in string
    return protocol and address and params


@bot.event
async def on_ready():
    print(f'{bot.user} подключен к Discord!')
    for guild in bot.guilds:
        print(
            f'{bot.user} подключились к чату:\n'
            f'{guild.name}(id: {guild.id})\n'
        )


@bot.command(name='play', pass_context=True)
async def play(ctx, *url):
    try:
        global player
        if len(url) == 0:
            return
        elif len(url) != 1 or not is_url(url[0]):
            url = ' '.join(url)
            if 'youtube.com' not in url:
                raise UrlError
            parts = '%20'.join(url.split())
            res = requests.get(
                f'https://youtube.googleapis.com/youtube/v3/search?part=snippet&maxResults=25&q={parts}&key={YOUTUBE_TOKEN}').json()
            id = res['items'][0]['id']['videoId']
            url = f'https://www.youtube.com/watch?v={id}'
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
                    discord.FFmpegPCMAudio(song_info["formats"][0]["url"], executable='ffmpeg.exe'))
                ctx.message.guild.voice_client.source = discord.PCMVolumeTransformer(ctx.message.guild.voice_client.source)
                ctx.message.guild.voice_client.source.volume = 1
                await ctx.message.channel.send('Сейчас играет:\n' + url)
            elif player.is_playing():
                await asyncio.sleep(1)
    except UrlError:
        await ctx.message.channel.send('Некорректная ссылка')
    except Exception as e:
        print(e)


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


@bot.command(pass_context=True, name='skip')
async def skip(ctx):
    global queue, player
    ctx.message.guild.voice_client.stop()
    if not queue.empty():
        await ctx.message.channel.send('Трек пропущен')


bot.run(TOKEN)
