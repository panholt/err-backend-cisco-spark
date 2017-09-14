# -*- coding: utf-8 -*-
import json
import logging
import sys
import re
import websocket

from errbot.core import ErrBot
# from errbot.backends.base import Message, Presence, ONLINE, AWAY, Room, \
# RoomError, RoomDoesNotExistError, UserDoesNotExistError, RoomOccupant, \
# Person, Card, Stream
from errbot.backends.base import Message, Person, Room, RoomOccupant
from errbot.rendering import md

import sparkpy

# Can't use __name__ because of Yapsy
log = logging.getLogger('errbot.backends.spark')

# Constants
NEWLINE_RE = re.compile(r'(?<!\n)\n(?!\n)')  # Single \n only, not \n\n


class SparkPerson(Person):
    '''
    This class represents a Person in Cisco Spark. This is a wrapper over
    sparkpy.models.people.SparkPerson
    '''

    def __init__(self, person):
        if isinstance(person, sparkpy.models.SparkPerson):
            self._person = person
        elif sparkpy.utils.is_api_id(person, 'people'):
            self._person = sparkpy.SparkPerson(person)
        else:
            raise TypeError('SparkPerson requires an id or sparkpy Person')

    @property
    def person(self):
        return self._person._id

    @property
    def client(self):
        return 'Cisco Spark'

    @property
    def nick(self):
        return self._person.emails[0]

    @property
    def aclattr(self):
        return self.nick

    @property
    def fullname(self):
        return self._person.displayName

    def __getattr__(self, attr):
        return getattr(self._person, attr)

    def __repr__(self):
        return '<SparkPerson("{}")>'.format(self.person)


class SparkRoomOccupant(SparkPerson, RoomOccupant):
    '''
    This object represents a member in a Spark Room
    '''
    def __init__(self, person, room):
        self._person = person
        self._room = room

    @property
    def room(self):
        return self._room

    @property
    def person(self):
        return self._person

    def __repr__(self):
        return '<SparkRoomOccupant({}/{})'.format(self.room, self.person)


class SparkMessage(Message):
    @property
    def is_direct(self):
        return self.to.roomType == 'direct'

    @property
    def is_group(self):
        return self.to.roomType == 'group'


class SparkBackend(ErrBot):
    '''
    The Spark backend for ErrBot
    '''

    def __init__(self, config):
        super().__init__(config)
        self.token = config.BOT_IDENTITY.get('token')
        if self.token:
            SESSION.headers = {'Content-type': 'application/json; charset=utf-8',
                               'Authorization': 'Bearer {}'.format(self.token)}
            SESSION.hooks = {'response': [retry_after_hook]}
        else:
            log.fatal('Cannot find API token.')
            sys.exit(1)

        self.bot_identifier = self.build_self_identitiy()
        self.md = md()
        self._webhook_id = None
        self._webhook_url = None
        self._webhook_secret = None
        self._rooms = SparkRoomList()
        self.ws = websocket.WebSocketApp(config.WEBSOCKET_PROXY,
                                         on_message=self.ws_message_callback,
                                         on_error=self.ws_error_callback,
                                         on_close=self.ws_close_callback)
        self.build_alt_prefixes()
        global BOT
        BOT = self

    @property
    def webhook_url(self):
        return self._webhook_url

    @webhook_url.setter
    def webhook_url(self, value):
        self._webhook_url = value
        return

    @property
    def webhook_id(self):
        return self._webhook_id

    @webhook_id.setter
    def webhook_id(self, value):
        self._webhook_id = value

    @property
    def webhook_secret(self):
        return self._webhook_secret

    @webhook_secret.setter
    def webhook_secret(self, value):
        self._webhook_secret = value

    @property
    def mode(self):
        return 'spark'

    def build_self_identitiy(self):
        resp = SESSION.get(API_BASE + 'people/me')
        if resp.status_code != 200:
            process_api_error
        else:
            data = resp.json()
            return SparkPerson(personId=data['id'],
                               personDisplayName=data['displayName'],
                               personEmail=data['emails'][0])

    def build_alt_prefixes(self):
        words = self.bot_identifier.personDisplayName.split(' ')
        new_prefixes = []
        if len(words) > 1:
            for x in range(len(words)):
                new_prefixes.append(' '.join(words[:x+1]))
        else:
            new_prefixes.append(self.bot_identifier.personDisplayName)

        try:
            bot_prefixes = self.bot_config.BOT_ALT_PREFIXES.split(',')
        except AttributeError:
            bot_prefixes = list(self.bot_config.BOT_ALT_PREFIXES)

        self.bot_alt_prefixes = tuple(new_prefixes + bot_prefixes)
        # Errbot wont consider alt prefixes if the key doesn't exist in the config
        if len(self.bot_config.BOT_ALT_PREFIXES) < 1:
            self.bot_config.BOT_ALT_PREFIXES = self.bot_alt_prefixes
        return

    def get_webhooks(self):
        log.debug('Fetching Webhooks')
        resp = SESSION.get(API_BASE + 'webhooks')
        if resp.status_code != 200:
            process_api_error(resp)
        data = resp.json()
        return data['items']

    def create_webhook(self, url, secret):
        url = url.replace('12345', '8443')
        data = {'name': 'Spark Errbot Webhook',
                'targetUrl': url,
                'resource': 'all',
                'event': 'all'}
        if secret:
            data['secret'] = secret
        resp = SESSION.post(API_BASE + 'webhooks', json=data)
        if resp.status_code != 200:
            process_api_error(resp)
        else:
            return resp.json().get('id')

    def delete_webhook(self, webhook_id):
        resp = SESSION.delete(API_BASE + 'webhooks/{}'
                              .format(webhook_id))
        if resp.status_code != 204:
            process_api_error(resp)
        self._webhook_id = None
        self._webhook_url = None
        self._webhook_secret = None
        return

    def clear_webhooks(self):
        for hook in self.get_webhooks():
            if hook['name'] == 'Spark Errbot Webhook':
                log.debug('Deleting Webhook: {}'.format(hook))
                self.delete_webhook(hook['id'])
        return

    def ws_message_callback(self, ws, message):
        try:
            event = json.loads(message)
        except ValueError:
            log.error('Invalid json received from websocket: {}'.format(event))
            return
        if event.get('url'):
            # First event received, should be our webhook url
            log.debug('Received new Webhook information event: {}'.format(event))
            log.debug('Clearing old webhooks')
            self.clear_webhooks()
            self.webhook_url = event.get('url')
            self.webhook_secret = event.get('secret')
            self.webhook_id = self.create_webhook(self.webhook_url, self.webhook_secret)

        elif event.get('data'):
            log.debug('Received event: {}'.format(event.get('data')))
            resource = event['data'].get('resource', 'None')
            if resource == 'messages':
                self.spark_message_callback(event['data'])
            elif resource == 'memberships':
                self.spark_memberships_callback(event['data'])
            elif resource == 'rooms':
                self.spark_rooms_callback(event['data'])
            elif resource == 'teams':
                self.spark_teams_callback(event['data'])
            else:
                log.debug('Unknown event type received: {}'.format(resource))
        else:
            log.debug('Unknown event received over websocket: {}'.format(event))
        return

    def ws_error_callback(self, ws, error):
        if self.webhook_id:
            self.delete_webhook(self.webhook_id)
        raise error

    def ws_close_callback(self, ws):
        if self.webhook_id:
            self.delete_webhook(self.webhook_id)
        return

    def spark_message_callback(self, event):
        if event['data']['personId'] != self.bot_identifier:
                # don't bother processing messages from the bot.
                message = self.decrypt_message(event['data']['id'])
                self.callback_message(message)
        return

    def spark_memberships_callback(self, event):
        log.debug('Membership event received')
        return

    def spark_rooms_callback(self, event):
        log.debug('Room event received')
        if event['event'] == 'updated':
            # Room has been updated, clear the cache
            if event['data']['id'] in self._rooms:
                del(self._rooms[event['data']['id']])
                # refresh 
                try:
                    self._rooms[event['data']['id']]
                except KeyError:
                    pass
        elif event['event'] == 'updated':
            # new room, update the cache
            try:
                self._rooms[event['data']['id']]
            except KeyError:
                pass
        return 

    def spark_teams_callback(self, event):
        log.debug('Team event received')
        return

    def build_identifier(self, text_representation, room_id=False):
        log.debug('Build Identifier called with {}'
                  .format(text_representation))
        if text_representation.startswith(PERSON_PREFIX):
            if room_id:
                return SparkRoomOccupant(self.query_room(room_id),
                                         personId=text_representation)
            else:
                return SparkPerson(personId=text_representation)
        elif '@' in text_representation:
            return SparkPerson(personEmail=text_representation)
        elif text_representation.startswith(ROOM_PREFIX):
            return self.query_room(text_representation)
        else:
            raise Exception('Invalid identifier')
        return

    def query_room(self, roomId):
        if roomId.startswith(ROOM_PREFIX):
            log.debug('Returning: {}'.format(self._rooms[roomId]))
            return self._rooms[roomId]
        else:
            raise ValueError('Query Room called with: {}. Does not match the prefix: {}'.format(roomId, ROOM_PREFIX))
        # The core plugin for create room expects a room object back
        # else:
        #     room = SparkRoom(roomId=None,
        #                      title=roomId,
        #                      roomType='group',
        #                      isLocked=False,
        #                      lastActivity=None,
        #                      created=None,
        #                      teamId=None
        #                      )
        #     return room

    def get_team_rooms(self, teamId):
        log.debug('Fetching team rooms for team: {}'.format(teamId))
        resp = SESSION.get(API_BASE + 'rooms', params={'teamId': teamId, 'sortBy': 'id'})
        log.debug('Got Response: {} Body: {}'.format(resp.status_code, resp.text))
        if resp.status_code == 200:
            data = get_all_pages(resp)
            return [SparkRoom(roomId=room['id'],
                                     title=room.get('title', ''),
                                     roomType=room['type'],
                                     isLocked=room['isLocked'],
                                     lastActivity=room['lastActivity'],
                                     created=room['created'],
                                     teamId=room.get('teamId'))
                    for room in data]
        else:
            process_api_error(resp)
        return

    def build_reply(self, message, text=None, direct=False):
        response = self.build_message(text)
        response.frm = self.bot_identifier
        # Errbot needs to know if a message is direct or in a room
        if message.is_group:
            response.to = message.frm.room
        else:
            response.to = message.frm
        return response

    def send_message(self, message, files=None):
        super().send_message(message)
        log.debug('Text is: {}'.format(message.body))
        data = {'markdown': self.md.convert(NEWLINE_RE.sub(r'  \n', message.body))}
        to = str(message.to)
        log.debug('Entered send_message with To: {}'.format(to))
        if message.is_direct:
            if '@' in to:
                data['toPersonEmail'] = to
            elif to.startswith(PERSON_PREFIX):
                data['toPersonId'] = to
        else:
            data['roomId'] = to
        log.debug('Sending message with payload: {}'.format(data))
        resp = SESSION.post(API_BASE + 'messages', json=data)
        if resp.status_code == 200:
            return
        else:
            process_api_error(resp)

    def send_card(self, card):
        '''
        Implement the send_card functionality for Cisco Spark.
        Cisco Spark doesn't really support cards or html formatting
        This is subject to breakage
        '''
        color_wheel = {'red': 'danger',
                       'yellow': 'warning',
                       'green': 'success',
                       'teal': 'info'}

        msg = '<blockquote class="{}">'.format(card.color or
                                               color_wheel.get(card.color, 'info'))
        msg += '<h2>{}</h2>'.format(card.title or '')
        msg += '{}</br>'.format(card.link)
        if card.fields:
            msg += '<ul>'
            for pair in card.fields:
                msg += '<li><b>{}:</b> {}</li>'.format(*pair)
            msg += '</ul>'
        msg += card.body or ''

        data = {'markdown': msg}
        data['roomId'] = card.to.room.roomId
        resp = SESSION.post(API_BASE + 'messages', json=data)
        if resp.status_code == 200:
            return
        else:
            process_api_error(resp)

    def change_presence(self, status, message):
        log.debug('Presence is not implemented by the Spark backend')
        return

    def decrypt_message(self, message_id):
        """
        Decrypt a message received from a webhook event

        :returns:
            An instance of :class:`~Message`.
        """

        resp = SESSION.get(API_BASE + 'messages/{}'.format(message_id))
        if resp.status_code != 200:
            process_api_error(resp)

        data = resp.json()
        text = data.get('text', '')

        message = SparkMessage(text)
        message.frm = self.build_identifier(data.get('personId'),
                                            room_id=data.get('roomId'))
        room = self.query_room(data.get('roomId'))
        message.to = self.build_identifier(room.roomId)
        return message

    def rooms(self):
        """
        Return a list of rooms the bot is currently in.

        :returns:
            A list of :class:`~SparkRoom` instances.
        """

        resp = SESSION.get(API_BASE + 'rooms')
        if resp.status_code == 200:
            data = get_all_pages(resp)
            rooms = []
            for room in data:
                rooms.append(SparkRoom(roomId=room['id'],
                                       title=room.get('title', ''),
                                       roomType=room['type'],
                                       isLocked=room['isLocked'],
                                       lastActivity=room['lastActivity'],
                                       created=room['created'],
                                       teamId=room.get('teamId')
                                       ))
            # Refresh the room cache
            self._rooms = SparkRoomList([(room.roomId, room)
                                         for room in rooms])
            return rooms
        else:
            process_api_error(resp)
        return

    def create_room_with_particpants(self, title, particpants):
        resp = SESSION.post(API_BASE + 'rooms', json={'title': title})
        data = resp.json()
        
        room = SparkRoom(roomId=data['id'],
                         title=data.get('title', ''),
                         roomType=data['type'],
                         isLocked=data['isLocked'],
                         lastActivity=data['lastActivity'],
                         created=data['created'],
                         teamId=data.get('teamId')
                         )
        if instance(particpants, list):
            for particpant in particpants:
                room.invite(particpant)
        else:
            room.invite(particpant)
        return room

    def serve_forever(self):
        log.debug('Entering serve forever')
        try:
            self.connect_callback()
            self.ws.run_forever(ping_interval=60)
        except KeyboardInterrupt:
            log.debug('KeyboardInterrupt received')
            pass
        except Exception as e:
            log.debug('Caught Exception: {}'.format(e))
        finally:
            log.info('Received keyboard interrupt. Shutdown requested.')
            self.ws.close()
            if self.webhook_id:
                log.debug('Deleting ephemeral webhook')
                self.delete_webhook(self.webhook_id)
            self.disconnect_callback()
            self.shutdown()
