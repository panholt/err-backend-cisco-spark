from errbot import BotPlugin, botcmd, arg_botcmd, webhook


class SparkWebhook(BotPlugin):
    """
    Webhook Receiver for Spark Backend
    """

    @webhook('/incoming')
    def incoming(self, request):
        self.log.debug('Got Request: {}'.format(request))

        handlers = {'messages': self.process_message,
                    'memberships': self.process_membership,
                    'rooms': self.process_room}
        handlers.get(request.get('resource'), self.process_unknown)(request)
        return "OK"

    def process_message(self, request):
        if request['data']['personId'] == self._bot.bot_identifier:
            #don't bother processing messages from the bot.
            return
        message = self._bot.decrypt_message(request['data']['id'])
        self.log.debug('To is group: {}'.format(message.is_group))
        self._bot.callback_message(message)
        return

    def process_membership(self, request):
        if request['event'] == 'deleted':
            if request['data']['personId'] == self._bot.bot_identifier:
                self.log.debug('Removed from room: {}'.format(request['data']['roomId']))
                self._bot._rooms.discard(self._bot.query_room(request['data']['roomId']))
            else:
                #TODO Not the bot, so don't really care until all the RoomOccupant stuff is implemented
                pass
        elif request['event'] == 'created':
            if request['data']['personId'] == self._bot.bot_identifier:
                self.log.debug('Added to room: {}'.format(request['data']['roomId']))
                self._bot._rooms.add(self._bot.query_room(request['data']['roomId']))
            else:
                #TODO see above
                pass
        return

    def process_room(self, request):
        #Probably the least interesting of the events. This indicates a title change, or moderation change.
        #Just refresh the bots rooms
        self._bot._rooms = set(self._bot.rooms())
        return

    def process_unknown(self, request):
        self.log.debug('Got unknown request: {}'.format(request))
        return
