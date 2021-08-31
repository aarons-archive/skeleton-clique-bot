#  Life
#  Copyright (C) 2020 Axel#3456
#
#  Life is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software
#  Foundation, either version 3 of the License, or (at your option) any later version.
#
#  Life is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
#  PARTICULAR PURPOSE.  See the GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License along with Life. If not, see https://www.gnu.org/licenses/.
#

from __future__ import annotations

import asyncio
import contextlib
import functools
from typing import Optional, TYPE_CHECKING

import async_timeout
import discord

import config
from utilities import context, paginators, utils

if TYPE_CHECKING:
    from bot import Life


class FilePaginator:

    def __init__(
            self, *, bot: Life = None, ctx: context.Context, entries: list[functools.partial], timeout: int = 300, delete_message_when_done: bool = False,
            delete_reactions_when_done: bool = True, header: Optional[str] = None, footer: Optional[str] = None
    ) -> None:

        self.bot: Life = bot or ctx.bot
        self.ctx: context.Context = ctx
        self.entries: list[functools.partial] = entries

        self.timeout: int = timeout
        self.delete_message_when_done: bool = delete_message_when_done
        self.delete_reactions_when_done: bool = delete_reactions_when_done

        self.reaction_event: asyncio.Event = asyncio.Event()

        self.task: Optional[asyncio.Task]= None
        self.message: Optional[discord.Message] = None

        self.looping: bool = True
        self.page: int = 0

        self.BUTTONS = {
            ':first:737826967910481931':    self.first,
            ':backward:737826960885153800': self.backward,
            ':stop:737826951980646491':     self.stop,
            ':forward:737826943193448513':  self.forward,
            ':last:737826943520473198':     self.last
        }

        self._header: Optional[str] = header
        self._footer: Optional[str] = footer

    # Properties

    @property
    def header(self) -> str:
        return self._header or f'\n\nPage: {self.page + 1}/{len(self.entries)} | Total entries: {len(self.entries)}\n'

    @property
    def footer(self) -> str:
        return self._footer or ''

    # Checks

    def check_reaction(self, payload: discord.RawReactionActionEvent) -> bool:

        if str(payload.emoji).strip('<>') not in self.BUTTONS.keys():
            return False

        if payload.message_id != getattr(self.message, 'id') or payload.channel_id != getattr(getattr(self.message, 'channel'), 'id'):
            return False

        return payload.user_id in {*config.OWNER_IDS, self.ctx.author.id}

    # Listeners

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:

        if not self.check_reaction(payload) or not self.looping:
            return

        self.reaction_event.set()
        with contextlib.suppress(paginators.AlreadyOnPage, paginators.PageOutOfBounds):
            await self.BUTTONS[str(payload.emoji).strip('<>')]()

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:

        if not self.check_reaction(payload) or not self.looping:
            return

        self.reaction_event.set()
        with contextlib.suppress(paginators.AlreadyOnPage, paginators.PageOutOfBounds):
            await self.BUTTONS[str(payload.emoji).strip('<>')]()

    # Loop

    async def loop(self) -> None:

        if len(self.entries) == 1:
            await self.message.add_reaction(':stop:737826951980646491')
        else:
            for emote in self.BUTTONS:
                await self.message.add_reaction(emote)

        #

        while self.looping:
            try:
                async with async_timeout.timeout(self.timeout):
                    await self.reaction_event.wait()
                    self.reaction_event.clear()
            except asyncio.TimeoutError:
                self.looping = False
            else:
                continue

        #

        if self.message and self.delete_reactions_when_done:
            for reaction in self.BUTTONS:
                await self.message.remove_reaction(reaction, self.bot.user)
            await self.stop(delete=False)
        else:
            await self.stop(delete=self.delete_message_when_done)

    # Page generator

    async def generate_page(self, page: int = 0) -> str:
        image = await utils.upload_image(bot=self.bot, file=await self.entries[page](page=page))
        return f'{self.header}{image}{self.footer}'

    # Abstract methods

    async def paginate(self) -> None:

        self.message = await self.ctx.reply(await self.generate_page(self.page))

        self.task = asyncio.create_task(self.loop())

        self.bot.add_listener(self.on_raw_reaction_add)
        self.bot.add_listener(self.on_raw_reaction_remove)

    async def first(self) -> None:

        if self.page == 0:
            raise paginators.AlreadyOnPage

        self.page = 0
        await self.message.edit(content=await self.generate_page(self.page))

    async def backward(self) -> None:

        if self.page <= 0:
            raise paginators.PageOutOfBounds

        self.page -= 1
        await self.message.edit(content=await self.generate_page(self.page))

    async def stop(self, delete: bool = True) -> None:

        self.task.cancel()
        self.looping = False

        if self.message and delete:
            await self.message.delete()
            self.message = None

        self.bot.remove_listener(self.on_raw_reaction_add)
        self.bot.remove_listener(self.on_raw_reaction_remove)

    async def forward(self) -> None:

        if self.page >= len(self.entries) - 1:
            raise paginators.PageOutOfBounds

        self.page += 1
        await self.message.edit(content=await self.generate_page(self.page))

    async def last(self) -> None:

        if (page := len(self.entries) - 1) == self.page:
            raise paginators.AlreadyOnPage

        self.page = page
        await self.message.edit(content=await self.generate_page(self.page))