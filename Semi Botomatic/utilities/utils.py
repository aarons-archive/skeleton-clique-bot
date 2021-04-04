from __future__ import annotations

import codecs
import datetime as dt
import logging
import os
import pathlib
from typing import TYPE_CHECKING, Union

import discord
import humanize
import mystbin
import pendulum
from pendulum.datetime import DateTime

import config

if TYPE_CHECKING:
    from bot import SemiBotomatic

__log__ = logging.getLogger(__name__)


async def safe_text(*, mystbin_client: mystbin.Client, text: str, max_characters: int = 1024) -> str:

    if len(text) <= max_characters:
        return text

    try:
        return await mystbin_client.post(text, syntax='python')
    except mystbin.APIError as error:
        __log__.warning(f'[ERRORS] Error while uploading error traceback to mystbin | Code: {error.status_code} | Message: {error.message}')
        return f'{text[:1024]}'


def convert_datetime(*, datetime: Union[dt.datetime, DateTime]) -> DateTime:
    return pendulum.instance(datetime, tz='UTC') if isinstance(datetime, dt.datetime) else datetime


def format_seconds(*, seconds: int, friendly: bool = False) -> str:

    minute, second = divmod(seconds, 60)
    hour, minute = divmod(minute, 60)
    day, hour = divmod(hour, 24)

    days, hours, minutes, seconds = round(day), round(hour), round(minute), round(second)

    if friendly is True:
        return f'{f"{days}d " if not days == 0 else ""}{f"{hours}h " if not hours == 0 or not days == 0 else ""}{minutes}m {seconds}s'

    return f'{f"{days:02d}:" if not days == 0 else ""}{f"{hours:02d}:" if not hours == 0 or not days == 0 else ""}{minutes:02d}:{seconds:02d}'


def format_datetime(*, datetime: Union[dt.datetime, DateTime], seconds: bool = False) -> str:
    datetime = convert_datetime(datetime=datetime)
    return datetime.format(f'dddd MMMM Do YYYY [at] hh:mm{":ss" if seconds else ""} A zz{"ZZ" if datetime.timezone.name != "UTC" else ""}')


def format_date(*, datetime: Union[dt.datetime, DateTime]) -> str:
    return convert_datetime(datetime=datetime).format('dddd MMMM Do YYYY')


def format_difference(*, datetime: Union[dt.datetime, DateTime], suppress=None) -> str:

    if suppress is None:
        suppress = ['seconds']

    return humanize.precisedelta(pendulum.now(tz='UTC').diff(convert_datetime(datetime=datetime)), format='%0.0f', suppress=suppress)


def person_avatar(*, person: Union[discord.User, discord.Member]) -> str:
    return str(person.avatar_url_as(format='gif' if person.is_avatar_animated() else 'png'))


def line_count() -> tuple[int, int, int, int]:

    files, functions, lines, classes = 0, 0, 0, 0
    is_docstring = False

    for dirpath, _, filenames in os.walk('.'):

        for filename in filenames:
            if not filename.endswith('.py'):
                continue
            files += 1

            # noinspection PyArgumentEqualDefault
            with codecs.open('./' + str(pathlib.PurePath(dirpath, filename)), 'r', 'utf-8') as filelines:
                filelines = [line.strip() for line in filelines]
                for line in filelines:

                    if len(line) == 0:
                        continue

                    if line.startswith('"""'):
                        is_docstring = not is_docstring
                    if is_docstring:
                        continue

                    if line.startswith('#'):
                        continue
                    if line.startswith(('def', 'async def')):
                        functions += 1
                    if line.startswith('class'):
                        classes += 1
                    lines += 1

    return files, functions, lines, classes


def badges(*, bot: SemiBotomatic, person: Union[discord.User, discord.Member]) -> str:

    badges_list = [badge for name, badge in config.BADGE_EMOJIS.items() if dict(person.public_flags)[name] is True]
    if dict(person.public_flags)['verified_bot'] is False and person.bot:
        badges_list.append('<:bot:738979752244674674>')

    if any(getattr(guild.get_member(person.id), 'premium_since', None) for guild in bot.guilds):
        badges_list.append('<:booster_level_4:738961099310760036>')

    if person.is_avatar_animated() or any(getattr(guild.get_member(person.id), 'premium_since', None) for guild in bot.guilds):
        badges_list.append('<:nitro:738961134958149662>')

    elif member := discord.utils.get(bot.get_all_members(), id=person.id):
        if activity := discord.utils.get(member.activities, type=discord.ActivityType.custom):
            if activity.emoji and activity.emoji.is_custom_emoji():
                badges_list.append('<:nitro:738961134958149662>')

    return ' '.join(badges_list) if badges_list else 'N/A'


def activities(*, person: discord.Member) -> str:

    if not person.activities:
        return 'N/A'

    message = '\n'
    for activity in person.activities:

        if activity.type == discord.ActivityType.custom:
            message += '• '
            if activity.emoji:
                message += f'{activity.emoji} '
            if activity.name:
                message += f'{activity.name}'
            message += '\n'

        elif activity.type == discord.ActivityType.playing:

            message += f'• Playing **{activity.name}** '
            if not isinstance(activity, discord.Game):
                if activity.details:
                    message += f'**| {activity.details}** '
                if activity.state:
                    message += f'**| {activity.state}** '
                message += '\n'

        elif activity.type == discord.ActivityType.streaming:
            message += f'• Streaming **[{activity.name}]({activity.url})** on **{activity.platform}**\n'

        elif activity.type == discord.ActivityType.watching:
            message += f'• Watching **{activity.name}**\n'

        elif activity.type == discord.ActivityType.listening:

            if isinstance(activity, discord.Spotify):
                url = f'https://open.spotify.com/track/{activity.track_id}'
                message += f'• Listening to **[{activity.title}]({url})** by **{", ".join(activity.artists)}** '
                if activity.album and activity.album != activity.title:
                    message += f'from the album **{activity.album}** '
                message += '\n'
            else:
                message += f'• Listening to **{activity.name}**\n'

    return message
