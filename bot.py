from discord import Embed
from discord.ext.commands import Bot, CommandError, dm_only
from mysql import connector
from mysql.connector import Error, errorcode

from datetime import datetime, timedelta
from email.mime.text import MIMEText
from json import load
from secrets import token_hex
from smtplib import SMTP_SSL
from typing import Optional


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
        super().__init__(command_prefix='!')

    async def on_command_error(self, ctx, exception):
        embed = generate_embed_template(ctx, 'Error Running Command', True)
        embed.description = str(exception)
        await ctx.send(embed=embed)


bot = AdmitBot()


@bot.command(brief='Verify your Discord account with your MyMIT email address.', help=(
    '`!verify` is used to verify your Discord account with your MyMIT email address before you are given access to the '
    'Discord server. To use the command, run `!verify` with your email address to request a verification token that '
    'will be sent to your email inbox. That email will give you the token needed to complete your account verification '
    'and give you full access to the server.\n\nIf you are already verified, running `!verify` with your email address '
    'will give you the role for full access to the server again in case you do not have it. If you have continued '
    'trouble gaining access to the server, please contact the server admins, who can reach out to the developers.'
))
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
            # Need to obtain discriminator from database for specified email
            cursor.execute("SELECT username, discriminator FROM users WHERE email = %s", (email,))
            username, discriminator = cursor.fetchone()
            if discriminator:
                if int(ctx.message.author.discriminator) == discriminator and ctx.message.author.name == username:
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
                msg['Subject'] = 'MyMIT Verification for MIT 2024 Discord Server'
                msg['From'] = 'SIPB Discord Verifier <sipb-discord-verifier@mit.edu>'
                msg['To'] = email
                smtp.sendmail('mit2024bot@mit.edu', email, msg.as_string())
                embed = generate_embed_template(ctx, 'Verification Requested Successfully')
                embed.description = 'Please check your inbox at `{}` for further instructions'.format(email)
                await ctx.send(embed=embed)
                return
            # Logic here has a token specified, so we attempt verification.
            # Get discriminator, token, and expiry for specified email
            else:
                cursor.execute("SELECT token, token_expiry FROM users WHERE email = %s", (email,))
                stored, expiry = cursor.fetchone()
                if stored != token:
                    raise CommandError("Token is incorrect! Double check and make sure it is correct.")
                elif expiry < datetime.now():
                    raise CommandError('Token has expired! Run `!verify {}` for a new token.'.format(email))
                else:
                    # Verified. For the specified email, set username and discriminator. Token and expiry should just be
                    # None.
                    username = ctx.message.author.name
                    discriminator = ctx.message.author.discriminator
                    cursor.execute("UPDATE users SET username = %s, discriminator = %s, token = NULL, " +
                                   "token_expiry = NULL WHERE email = %s", (username, discriminator, email))
                    connection.commit()
                    await finish_verification(ctx)
                    return
        else:
            raise CommandError('Email `{}` was not recognized as a valid MyMIT email'.format(email))
    finally:
        connection.close()

bot.run(Config['discord']['token'])
