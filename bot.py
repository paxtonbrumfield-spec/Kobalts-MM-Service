import os
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands, tasks

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

ADDRESSES = {
    "btc": "bc1q4dhd9hyeha383jsupvq9qwsmwpfj0d7lskllr0",
    "ltc": "LLyz7ZfbzxZMS59DWJFbViaehcLY7ec3MB",
    "sol": "5YgDLvXFui2gMUGwEVcTLj3k43oWSn2EZwbXDJTwefps",
    "usdt": "0x2DaEA564D6169D3366DB944D232479073802464B",
}

TOS = """# KOBALTS MIDDLEMAN TOS!!

If money is being sent through crypto you must wait for the money to confirm before releasing the account. If the money is not confirmed and you release and anything happens, it is your responsibility and you are completely liable.

All trades have a **$2 fee** unless the value is over **$100**.

The account must be on an Outlook or other email-changeable account (first mail or other small secure emails are acceptable).

After funds have been sent to my address, please **screenshot it and send me the transaction ID**.
"""

last_seen = {
    "btc": set(),
    "ltc": set(),
    "sol": set(),
    "usdt": set(),
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def make_embed(coin: str, address: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"Kobalts Middleman — {coin.upper()}",
        description=TOS,
        color=0x00ff88,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name=f"{coin.upper()} Address", value=f"`{address}`", inline=False)
    embed.add_field(
        name="Instructions",
        value=(
            "1. Send the exact amount + $2 fee (if under $100)\n"
            "2. Wait for confirmations\n"
            "3. Screenshot the transaction and send the **TXID** here"
        ),
        inline=False
    )
    embed.set_footer(text="Kobalts Middleman • Always wait for confirmations")
    return embed

async def notify(message: str):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print("Sync error:", e)
    check_payments.start()

@bot.tree.command(name="btc", description="Post BTC address + TOS")
async def btc_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=make_embed("btc", ADDRESSES["btc"]))

@bot.tree.command(name="ltc", description="Post LTC address + TOS")
async def ltc_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=make_embed("ltc", ADDRESSES["ltc"]))

@bot.tree.command(name="sol", description="Post SOL address + TOS")
async def sol_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=make_embed("sol", ADDRESSES["sol"]))

@bot.tree.command(name="usdt", description="Post USDT (ERC-20) address + TOS")
async def usdt_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=make_embed("usdt", ADDRESSES["usdt"]))

@bot.tree.command(name="vouch", description="Post a vouch message for the customer to copy")
@app_commands.describe(message="The vouch text you want them to copy and paste")
async def vouch_cmd(interaction: discord.Interaction, message: str):
    response = f"**Please copy and paste this vouch:**\n\n```{message}```"
    await interaction.response.send_message(response)

@tasks.loop(minutes=2)
async def check_payments():
    async with aiohttp.ClientSession() as session:
        try:
            await check_btc(session)
            await check_ltc(session)
            await check_sol(session)
        except Exception as e:
            print("Payment check error:", e)

async def check_btc(session):
    url = f"https://mempool.space/api/address/{ADDRESSES['btc']}/txs"
    async with session.get(url) as resp:
        if resp.status != 200:
            return
        txs = await resp.json()
        for tx in txs[:6]:
            txid = tx["txid"]
            if txid in last_seen["btc"]:
                continue
            received = 0
            for vout in tx.get("vout", []):
                if vout.get("scriptpubkey_address") == ADDRESSES["btc"]:
                    received += vout.get("value", 0)
            if received > 0:
                last_seen["btc"].add(txid)
                status = "Pending" if not tx.get("status", {}).get("confirmed") else "Confirmed"
                await notify(f"**BTC Payment Detected**\nAmount: `{received / 1e8:.8f} BTC`\nStatus: **{status}**\nTX: `{txid}`")

async def check_ltc(session):
    url = f"https://api.blockcypher.com/v1/ltc/main/addrs/{ADDRESSES['ltc']}/full?limit=6"
    async with session.get(url) as resp:
        if resp.status != 200:
            return
        data = await resp.json()
        for tx in data.get("txs", []):
            txid = tx["hash"]
            if txid in last_seen["ltc"]:
                continue
            received = 0
            for out in tx.get("outputs", []):
                if ADDRESSES["ltc"] in out.get("addresses", []):
                    received += out.get("value", 0)
            if received > 0:
                last_seen["ltc"].add(txid)
                status = "Confirmed" if tx.get("confirmations", 0) > 0 else "Pending"
                await notify(f"**LTC Payment Detected**\nAmount: `{received / 1e8:.8f} LTC`\nStatus: **{status}**\nTX: `{txid}`")

async def check_sol(session):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [ADDRESSES["sol"], {"limit": 8}]
    }
    async with session.post("https://api.mainnet-beta.solana.com", json=payload) as resp:
        if resp.status != 200:
            return
        data = await resp.json()
        for item in data.get("result", []):
            sig = item["signature"]
            if sig in last_seen["sol"]:
                continue
            last_seen["sol"].add(sig)
            await notify(f"**SOL Activity Detected**\nSignature: `{sig}`\n(Check Solscan for exact amount)")

bot.run(TOKEN)
