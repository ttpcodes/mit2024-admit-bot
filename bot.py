import mysql.connector
from mysql.connector import errorcode

from discord import Embed
from discord.ext.commands import Bot, command, CommandError

from datetime import datetime, timedelta
from email.mime.text import MIMEText
from secrets import token_hex
from smtplib import SMTP_SSL
from typing import Optional

DEFAULT_ROLE_USER_DATA = []
USER = "user"
PASS = "password"
HOST = "sql.mit.edu"
DB_NAME = "emmabat+mit2024"


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

    @command(brief='Verify your Discord account for a Guild.')
    async def verify(self, ctx, email: str, token: Optional[str]):
        try:
            connection = mysql.connector.connect(
                user=USER, 
                password = PASS,
                host = HOST,
                database=DB_NAME)
            cursor = connection.cursor()
            query = ("SELECT EXISTS(SELECT * FROM `{}` WHERE email = \'{}\')".format("users", email))
            cursor.execute(query)
            email_exists = cursor.fetchone()[0]
            if email_exists:
                # Need to obtain discriminator from database for specified email
                query = ("SELECT discriminator FROM `{}` WHERE email = '{}'".format("users", email))
                cursor.execute(query)
                discriminator = cursor.fetchone()[0]
                if not token:
                    if discriminator:
                        raise CommandError('Email `{}` is already associated with a Discord account'.format(email))
                    else:
                        gen = token_hex(32)
                        expiry = datetime.now() + timedelta(hours=24)
                        # TODO put gen, expiry into database
                        query = ("UPDATE users SET token = '{}', token_expiry = '{}' "
                                "WHERE email = '{}'".format(gen, expiry, email))
                        cursor.execute(query)
                        connection.commit()
                        # Set token = gen and expiry = expiry for specified email.
                        smtp = SMTP_SSL('outgoing.mit.edu')
                        smtp.login('', '') # TODO: config file
                        msg = MIMEText('Hello!<br><br>\n' +
                                    'To verify your email address, please send the following command to the bot:<br>\n' +
                                    '<pre>!verify {} {}</pre><br><br>\n'.format(email, gen), 'html')
                        msg['Subject'] = 'Discord - MyMIT Verification'
                        msg['From'] = 'Discord - MyMIT Bot <mit2024bot@mit.edu>'
                        msg['To'] = email
                        smtp.sendmail('mit2024bot@mit.edu', email, msg.as_string())
                        embed = generate_embed_template(ctx, 'Verification Requested Successfully')
                        embed.description = 'Please check your inbox at `{}` for further instructions'.format(email)
                        await ctx.send(embed=embed)
                        return
                # Logic here has a token specified, so we attempt verification.
                # Get discriminator, token, and expiry for specified email
                else:
                    if discriminator:
                        raise CommandError('Email `{}` is already associated with a Discord account'.format(email))
                    
                    query = ("SELECT token, token_expiry FROM users WHERE email = '{}'".format(email))
                    cursor.execute(query)
                    expiry, stored = cursor.fetchone()

                    if expiry < datetime.now():
                        raise CommandError('Token has expired! Run `!verify {}` for a new token.'.format(email))
                    elif stored != token:
                        raise CommandError("Token is incorrect! Double check and make sure it is correct.")
                    else:
                        # Verified. For the specified email, set username and discriminator. Token and expiry should just be
                        # None.
                        username = ctx.message.author.name
                        discriminator = ctx.message.author.discriminator
                        query = ("UPDATE users SET username = '{}', discriminator = '{}', "
                                "token = NULL, token_expiry = NULL, "
                                "WHERE email = '{}'".format(username, discriminator, email))
                        cursor.execute(query)
                        connection.commit()
                        # TODO put username, discriminator into database; set token, expiry to NULL
                        embed = generate_embed_template(ctx, 'Account Verified Successfully')
                        embed.description = "Contact the admins if you still can't access the server."
                        await ctx.send(embed=embed)
                        return
            else:
                raise CommandError('Email `{}` was not recognized as a valid MyMIT email'.format(email))
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                raise CommandError("Check your username or password.")
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                raise CommandError("Database does not exist.")
            else:
                raise CommandError(err)
        else:
            connection.close()
