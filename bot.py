from discord import Embed
from discord.ext.commands import Bot, command, CommandError

from datetime import datetime, timedelta
from email.mime.text import MIMEText
from secrets import token_hex
from smtplib import SMTP_SSL
from typing import Optional

DEFAULT_ROLE_USER_DATA = []


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
        if not token:
            try:
                # Need to obtain discriminator from database for specified email
                if discriminator:
                    raise CommandError('Email `{}` is already associated with a Discord account'.format(email))
                else:
                    gen = token_hex(32)
                    expiry = datetime.now() + timedelta(hours=24)
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
            except ProgrammingError:
                raise CommandError('Email `{}` was not recognized as a valid MyMIT email'.format(email))
        # Logic here has a token specified, so we attempt verification.
        # Get discriminator, token, and expiry for specified email
        try:
            if discriminator:
                raise CommandError('Email `{}` is already associated with a Discord account'.format(email))
            elif expiry < datetime.now():
                raise CommandError('Token has expired! Run `!verify {}` for a new token.'.format(email))
            elif stored != token:
                raise CommandError("Token is incorrect! Double check and make sure it is correct.")
            else:
                # Verified. For the specified email, set username and discriminator. Token and expiry should just be
                # None.
                username = ctx.message.author.name
                discriminator = ctx.message.author.discriminator
                embed = generate_embed_template(ctx, 'Account Verified Successfully')
                embed.description = "Contact the admins if you still can't access the server."
                await ctx.send(embed=embed)
                return
        except ProgrammingError:
            raise CommandError('Email `{}` was not recognized as a valid MyMIT email'.format(email))
