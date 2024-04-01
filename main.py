import re
from json import load, dump
from time import mktime
import requests
from bs4 import BeautifulSoup
from discord.ext import commands, tasks
from discord.flags import Intents
from discord import Embed, Colour
import aiohttp
from datetime import datetime

bot = commands.Bot(command_prefix='!!', intents=Intents.all())

# Some variables
data_path: str = "data.json"
with open(data_path, "r") as f:
    data = load(f)
    show_discount_games: bool = data["show_discount_games"]
    last_seen: list[int] = data["last_seen"]
    print(last_seen)
seen: list[int] = []
API_KEY: str = ""  # Steam API key
applisturl: str = f"https://api.steampowered.com/ISteamApps/GetAppList/v2/?key={API_KEY}"
priceurl: str = "https://store.steampowered.com/api/appdetails?filters=price_overview&appids="
appdetailsurl: str = "https://store.steampowered.com/api/appdetails?appids="
discount: dict = {}  # Games with a discount
free: dict = {}  # Giveaways


@bot.event
async def on_ready():
    print(f'Бот подключен как {bot.user.name} (ID: {bot.user.id})')
    print('------')
    await check_for_new_game.start()


@bot.command(aliases=("Привет", "привет", "Приветик", "приветик"))
async def hi(ctx: commands.Context):
    print(f"Said Приветик to {ctx.author}")
    await ctx.reply("Приветик")


@bot.command(aliases=("добавить", "add"))
async def add_channel(ctx: commands.Context, channel_id: int = 0):
    if not channel_id:
        channel_id: int = ctx.channel.id
    with open(data_path, "r+") as file:
        data = load(file)
        if channel_id not in data["channels"]:
            data['channels'].append(channel_id)
        file.seek(0)
        dump(data, file, indent=2)
        file.truncate()
    await ctx.reply(f"Канал (ID: {channel_id}) добавлен в список")


@bot.command(aliases=("удалить", "remove"))
async def remove_channel(ctx: commands.Context, channel_id: int = 0):
    if not channel_id:
        channel_id: int = ctx.channel.id
    with open(data_path, "r+") as file:
        data = load(file)
        if channel_id in data["channels"]:
            data['channels'].remove(channel_id)
        file.seek(0)
        dump(data, file, indent=2)
        file.truncate()
    await ctx.reply(f"Канал (ID: {channel_id}) удалён из списка")


async def fetch_data(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()


async def get_price(appid: str) -> dict:
    global price
    try:
        price = await fetch_data(priceurl + str(appid))
        return price["data"]["price_overview"]
    except KeyError:
        return price
    except Exception as e:
        return await get_price(appid)


@bot.command(aliases=("показывать_скидки", "скидки"))
async def show_discounts(ctx: commands.Context, value: bool = None):
    global show_discount_games
    if value is not None:
        show_discount_games = bool(value)
        with open(data_path, "r+") as file:
            data = load(file)
            data["show_discount_games"] = show_discount_games
            file.seek(0)
            dump(data, file, indent=2)
            file.truncate()
        await ctx.reply(f"Теперь игры со скидкой {'Показываются' if show_discount_games else 'Не показываются'}")
    else:
        await ctx.reply(
            f"На данный момент игры со скидкой {'Показываются' if show_discount_games else 'Не показываются'}"
        )


def get_final_date(appid: int) -> str:
    url = "https://store.steampowered.com/app/" + str(appid)
    soup = BeautifulSoup(requests.get(url).text, features="html.parser")
    data = soup.find("p", class_="game_purchase_discount_countdown")
    if data is not None:
        if not data.find("span"):  # Future
            date = mktime(datetime.strptime(" ".join(data.text.split()[-2:]), "%d %B").replace(
                year=datetime.now().year).timetuple())
            return f"<t:{int(date)}:R>"
        else:
            script = data.parent.find("script").__str__()
            if script != "None":  # If soon
                unixtime = re.search(r"InitDailyDealTimer\( \$DiscountCountdown, (\d{10}) \)", script)
                date = mktime(datetime.fromtimestamp(int(unixtime.group(1))).timetuple())
                return f"<t:{int(date)}:R>"
    else:  # Free
        data = soup.find("p", class_="game_purchase_discount_quantity").text.split("\n")[1].lstrip().split()

        date = mktime(datetime.strptime(f"{data[-6]} {data[-5]} {data[-3]}", "%d %b %H:%M%p.").replace(
            year=datetime.now().year).timetuple())
        return f"<t:{int(date)}:R>"


@tasks.loop()
async def check_for_new_game():
    global price, last_seen, seen
    json_data = await fetch_data(applisturl)
    for app in json_data['applist']['apps']:
        try:
            app["appid"]: int
            game_is_free: bool = False
            price = await get_price(app['appid'])
            if not price[str(app['appid'])]["success"]:
                continue
            if not price[str(app["appid"])]["data"]:
                continue
            if price[str(app['appid'])]['data']['price_overview']['discount_percent'] != 0:

                if app["appid"] in last_seen:
                    seen.append(app["appid"])
                    last_seen.remove(app["appid"])
                    print(f"{app['appid']} is skipped")
                    continue
                else:
                    last_seen.append(app["appid"])
                if price[str(app['appid'])]['data']['price_overview']['discount_percent'] == 100:
                    free[app['appid']] = price
                    print(datetime.now(), price)
                    game_is_free = True
                else:
                    discount[app['appid']] = price
                    print(datetime.now(), price)
                with open(data_path, "r") as file:
                    channels: list = load(file)["channels"]
                if show_discount_games and not game_is_free:
                    embed = Embed(
                        colour=Colour.from_rgb(12, 60, 116),
                        title=app["name"],
                        url="https://store.steampowered.com/app/" + str(app["appid"]),
                        description=f"""Цена без скидки: {price[str(app['appid'])]['data']['price_overview']['initial_formatted']}\nЦена со скидкой: {price[str(app['appid'])]['data']['price_overview']['final_formatted']}\nСкидка в процентах: {price[str(app['appid'])]['data']['price_overview']['discount_percent']}%\nДо: {get_final_date(app['appid'])}""",
                    )
                    embed.set_image(url=requests.get(appdetailsurl + str(app["appid"])).json()[str(app["appid"])]
                    ["data"]["header_image"])
                elif game_is_free:
                    embed = Embed(
                        colour=Colour.from_rgb(12, 60, 116),
                        title=app["name"],
                        url="https://store.steampowered.com/app/" + str(app["appid"]),
                    )
                    embed.set_image(url=requests.get(appdetailsurl + str(app["appid"])).json()[str(app["appid"])]
                    ["data"]["header_image"])
                else:
                    continue
                for channel in channels:
                    await bot.get_channel(channel).send(embed=embed)
        except Exception as e:
            print(e)
            continue
    last_seen = seen
    seen = []


if __name__ == "__main__":
    bot.run('')  # Discord bot token
    print(datetime.now(), "Discount:", discount)
    print(datetime.now(), "Free:", free)

    with open("output.txt", "a") as f:
        f.write(f"{datetime.now()} \nDiscount: {discount}, \nFree: {free}")
    with open("data.json", "r") as f:
        data = load(f)
        last_seen.extend(seen)
        data["last_seen"] = last_seen
    with open("data.json", "w") as f:
        dump(data, f, indent=2)
