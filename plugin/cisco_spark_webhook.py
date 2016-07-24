# -*- coding: utf-8 -*-
from errbot import BotPlugin, botcmd, arg_botcmd, webhook, SeparatorArgParser


class SparkWebhook(BotPlugin):
    """
    Webhook Receiver for Spark Backend
    """

    @webhook('/incoming')
    def incoming(self, request):
        self.log.debug('Got Request: {}'.format(request))

        handlers = {'messages': self.process_message_event,
                    'memberships': self.process_membership_event,
                    'rooms': self.process_room_event}
        handlers.get(request.get('resource'), self.process_unknown)(request)
        return "OK"

    def process_message_event(self, request):
        if request['data']['personId'] == self._bot.bot_identifier:
            # don't bother processing messages from the bot.
            return
        message = self._bot.decrypt_message(request['data']['id'])
        self.log.debug('To is group: {}'.format(message.is_group))
        self._bot.callback_message(message)
        return

    def process_membership_event(self, request):
        if request['event'] == 'deleted':
            if request['data']['personId'] == self._bot.bot_identifier:
                self.log.debug('Removed from room: {}'
                               .format(request['data']['roomId']))
                if request['data']['roomId'] in self._bot._rooms.keys():
                    del self._bot._rooms[request['data']['roomId']]

        elif request['event'] == 'created':
            if request['data']['personId'] == self._bot.bot_identifier:
                self.log.debug('Added to room: {}'
                               .format(request['data']['roomId']))
                # Call get to create the room in the backend cache
                self._bot._rooms.get(request['data']['roomId'])
        return

    def process_room_event(self, request):
        if request['event'] == 'created':
            self._bot._rooms.get(request['data']['roomId'])
        else:
            # Only other options are 'updated' and 'deleted'
            # Both require a delete on the cache
            if request['data']['roomId'] in self._bot._rooms.keys():
                del self._bot._rooms[request['data']['roomId']]
            # If its an update then update the cache
            elif request['event'] == 'updated':
                self._bot._rooms.get(request['data']['roomId'])
        return

    def process_unknown(self, request):
        self.log.debug('Got unknown request: {}'.format(request))
        return

    @botcmd(split_args_with=SeparatorArgParser())
    def spark_room_list(self, message, args):
        '''
        List chatrooms the bot has joined.
        Usage:
        /room list
        Examples:
        /room list
        '''
        rooms = [room.title for room in self._bot._rooms.values()]
        if len(rooms):
            return 'I\'m currently in these rooms:\n\t' + \
                    '{}'.format('\n\t'.join(rooms))
        else:
            return "I'm not currently in any rooms."

    @botcmd(split_args_with=SeparatorArgParser())
    def spark_room_leave(self, message, args):
        '''
        List chatrooms the bot has joined.
        Usage:
        /spark room list
        Examples:
        /spark room list
        '''
        rooms = [room.title for room in self._bot._rooms.values()]
        if args[0].startswith('Y2lzY29zcGFyazovL3VzL1JPT00'):  # Room prefix
            self._bot._rooms[args[0]].leave()
            return 'Left {}'.format(self._bot_rooms[args[0]].title)
        elif args[0].isdigit():
            list(self._bot._rooms.values())[int(args[0]) - 1].leave()
            return 'Left {}'.format(rooms[int(args[0]) - 1].title)
        else:
            yield 'Unknown room: {}'.format(args[0])
            yield 'Room must be a Spark Room Id or Index from /spark room list'
