from bs4 import BeautifulSoup
from discord import Embed
from discord.ext.commands import Bot, CommandError, dm_only
from discord.utils import get
from mysql import connector
from mysql.connector import Error, errorcode
from requests import get

from asyncio import sleep
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from json import load
from secrets import token_hex
from smtplib import SMTP_SSL
from typing import Optional


INPUT_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.000Z'
OUTPUT_DATE_FORMAT = '%H:%M'
SLEEP_TIME = 300


with open('config.json') as fp:
    Config = load(fp)


async def finish_verification(ctx):
    guild = ctx.bot.get_guild(Config['discord']['guild'])
    await guild.get_member(ctx.message.author.id).add_roles(guild.get_role(Config['discord']['role']))
    embed = generate_embed_template(ctx, 'Account Verified Successfully')
    embed.description = "Contact the admins if you still can't access the server."
    await ctx.send(embed=embed)


def generate_embed_template(ctx, title, error=False):
    embed = Embed(colour=16711680 if error else 32768, title=title)
    embed.timestamp = datetime.utcnow()
    embed.set_author(name=str(ctx.author), icon_url=str(ctx.author.avatar_url))
    embed.set_footer(text=str(ctx.me), icon_url=str(ctx.me.avatar_url))
    return embed


class AdmitBot(Bot):
    def __init__(self):
        super().__init__(command_prefix='!', help_command=None)
        self.loop.create_task(self.post_events())

    async def on_command_error(self, ctx, exception):
        embed = generate_embed_template(ctx, 'Error Running Command', True)
        embed.description = str(exception)
        await ctx.send(embed=embed)

    async def on_member_join(self, member):
        if not get(member.roles, id=Config['discord']['role']):
            embed = Embed(colour=32768, title='Welcome to the 2025 Admit Discord Server!')
            embed.timestamp = datetime.utcnow()
            embed.set_author(name=str(member), icon_url=str(member.avatar_url))
            embed.set_footer(text=str(self.user), icon_url=str(self.user.avatar_url))
            embed.description = ('Hi! I am Swole Tim, defender of the Discord. I use my big arms to hold off people '
                                 "who shouldn't be here and to hug people who should, and I have lumbered into your "
                                 'DMs to help with that.\n\nIn order to prove you are an adMIT, and worthy of hugs, '
                                 'please type `!verify <email address>` below, for whatever email address you used in '
                                 'the MIT Application Portal. I will then email you a verification code to send back to me. It may take a '
                                 'little bit of time to be delivered (especially if you use Yahoo!, for some reason), '
                                 "but it should get there. \n\nOnce you receive the email, please copy/paste the '
                                 'verification command and alphanumeric string back here, in the message field below. '
                                 'I will then use all my considerable strength to yeet you into the server with the '
                                 'other adMITs where you belong. If, for some reason, you have continued trouble '
                                 'gaining access to the server, please contact `sipb-discord@mit.edu` to assist.\n\n'
                                 'Once you\'re in the server, please check out #rules-n-how-to-discord, get roles in'
                                 '#roles, and don\'t forget to introduce yourself to your fellow adMITs in #introductions!')
            await member.send(embed=embed)

    async def post_events(self):
        while True:
            url = 'https://api.pathable.co/v1/meetings?apiKey={}'.format(Config['apiKey'])
            cal = get(url).json()
            data = cal['data']

            for item in data:
                start = datetime.strptime(item['startsAt'], INPUT_DATE_FORMAT)
                if datetime.now() + timedelta(minutes=5) > start:
                    embed = Embed(colour=32768, title='Upcoming Event in <=5 Minutes: {}'.format(item['name']))
                    embed.timestamp = datetime.utcnow()
                    embed.set_author(name=str(self.user), icon_url=str(self.user.avatar_url))
                    embed.set_footer(text=str(self.user), icon_url=str(self.user.avatar_url))
                    if 'description' in item:
                        embed.description = BeautifulSoup(item['description'], 'html.parser').text
                    embed.add_field(name='Start Time', value=start.strftime(OUTPUT_DATE_FORMAT))
                    embed.add_field(name='End Time', value=datetime.strptime(item['_endsAt'], INPUT_DATE_FORMAT)
                                    .strftime(OUTPUT_DATE_FORMAT))
                    embed.add_field(name='Link', value='https://cpw2020.mit.edu/meetings/{}'.format(item['_id']))
                    await self.get_guild(Config['discord']['guild']).get_channel(Config['discord']['channel'])\
                        .send(embed=embed)

            await sleep(SLEEP_TIME)


bot = AdmitBot()


@bot.command(name='help')
async def help_command(ctx):
    embed = generate_embed_template(ctx, 'MIT Application Portal Email Address Verification')
    embed.description = (
        '```!verify <email address> [token]```\n\n'
        '`!verify` is used to verify your Discord account with your MIT Application Portal email address before you are given '
        'access to the Discord server. To use the command, run `!verify` with your email address to request a '
        'verification token that will be sent to your email inbox. That email will give you the token needed to '
        'complete your account verification and give you full access to the server.\n\nIf you are already '
        'verified, running `!verify` with your email address will give you the role for full access to the server '
        'again in case you do not have it. If you have continued trouble gaining access to the server, please '
        'contact the server admins, who can reach out to the developers.'
    )
    await ctx.send(embed=embed)


@bot.command()
@dm_only()
async def verify(ctx, email: str, token: Optional[str]):
    try:
        connection = connector.connect(
            user=Config['database']['username'],
            password=Config['database']['password'],
            host=Config['database']['host'],
            database=Config['database']['database'])
    except Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            raise CommandError("Check your username or password.")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            raise CommandError("Database does not exist.")
        else:
            raise CommandError(err)
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT EXISTS(SELECT * FROM users WHERE email = %s)", (email,))
        email_exists = cursor.fetchone()[0]
        if email_exists:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            user_id = cursor.fetchone()[0]
            if user_id:
                if int(ctx.message.author.id) == user_id:
                    await finish_verification(ctx)
                else:
                    raise CommandError('Email `{}` is already associated with a Discord account'.format(email))
            elif not token:
                gen = token_hex(32)
                expiry = datetime.now() + timedelta(hours=24)
                cursor.execute("UPDATE users SET token = %s, token_expiry = %s WHERE email = %s",
                               (gen, expiry, email))
                connection.commit()
                # Set token = gen and expiry = expiry for specified email.
                smtp = SMTP_SSL('outgoing.mit.edu')
                smtp.login(Config['smtp']['username'], Config['smtp']['password'])
                msg = MIMEText('Hello!<br><br>\n' +
                               'To verify your email address, please send the following command to the bot:' +
                               '<br>\n<pre>!verify {} {}</pre><br><br>\n'.format(email, gen), 'html')
                msg['Subject'] = 'MIT Application Portal Verification for MIT 2025 Discord Server'
                msg['From'] = 'SIPB Discord Verifier <sipb-discord-verifier@mit.edu>'
                msg['To'] = email
                smtp.sendmail('mit2024bot@mit.edu', email, msg.as_string())
                embed = generate_embed_template(ctx, 'Verification Requested Successfully')
                embed.description = 'Please check your inbox at `{}` for further instructions'.format(email)
                await ctx.send(embed=embed)
                return
            # Logic here has a token specified, so we attempt verification.
            else:
                cursor.execute("SELECT token, token_expiry FROM users WHERE email = %s", (email,))
                stored, expiry = cursor.fetchone()
                if stored != token:
                    raise CommandError("Token is incorrect! Double check and make sure it is correct.")
                elif expiry < datetime.now():
                    raise CommandError('Token has expired! Run `!verify {}` for a new token.'.format(email))
                else:
                    cursor.execute("UPDATE users SET id = %s, token = NULL, " +
                                   "token_expiry = NULL WHERE email = %s", (ctx.message.author.id, email))
                    connection.commit()
                    await finish_verification(ctx)
                    return
        else:
            raise CommandError('Email `{}` was not recognized as a valid MIT Application Portal email (make sure your email does not '
                               'include angle brackets `<>`)'.format(email))
    finally:
        connection.close()

bot.run(Config['discord']['token'])
