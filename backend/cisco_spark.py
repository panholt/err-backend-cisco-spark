# -*- coding: utf-8 -*-
import json
import logging
import re

from errbot.core import ErrBot
from errbot.backends.base import Message, Person, Room, RoomOccupant
from errbot.rendering import md
import websocket
import sparkpy

# Can't use __name__ because of Yapsy
log = logging.getLogger('errbot.backends.spark')

# Constants
NEWLINE_RE = re.compile(r'(?<!\n)\n(?!\n)')  # Single \n only, not \n\n


class ErrSparkPerson(Person):
    '''
    This class represents a Person in Cisco Spark. This is a wrapper over
    sparkpy.models.people.SparkPerson
    '''

    def __init__(self, person):
        if isinstance(person, sparkpy.SparkPerson):
            self._sparkpy_person = person
        elif sparkpy.utils.is_api_id(person, 'people'):
            self._sparkpy_person = sparkpy.SparkPerson(person)
        else:
            raise TypeError('Invalid Cisco Spark Person id: ' + person)

    @property
    def person(self):
        return self._sparkpy_person._id

    @property
    def client(self):
        return 'Cisco Spark'

    @property
    def nick(self):
        return self._sparkpy_person.emails[0]

    @property
    def aclattr(self):
        return self.nick

    @property
    def fullname(self):
        return self._sparkpy_person.displayName

    def __getattr__(self, attr):
        return getattr(self._sparkpy_person, attr)

    def __repr__(self):
        return '<ErrSparkPerson("{person}")>'.format(person=self.person)


class ErrSparkRoom(Room):
    '''
    This object represents a Spark Room
    '''
    def __init__(self, room):
        if isinstance(room, sparkpy.SparkRoom):
            self._sparkpy_room = room
        if sparkpy.utils.is_api_id(room, 'rooms'):
            self._sparkpy_room = sparkpy.SparkRoom(room)
        else:
            raise TypeError('Invalid Cisco Spark Room id: ' + room)

    def join(self):
        raise NotImplemented('Cannot join rooms. Must be added instead')

    def leave(self):
        self._sparkpy_room.remove_member(self.spark.me.id)

    def create(self):
        pass

    def destroy(self):
        self._sparkpy_room.remove_all_members()
        self._sparkpy_room.delete()

    def exists(self):
        return True

    def joined(self):
        return True

    @property
    def topic(self):
        if self._sparkpy_room.type == 'direct':
            raise ValueError('Cannot change the title of a direct room')
        return self._sparkpy_room.title

    @topic.setter
    def topic(self, val):
        if self._sparkpy_room.type == 'direct':
            raise ValueError('Cannot change the title of a direct room')
        self._sparkpy_room.title = val
        return

    @property
    def occupants(self):
        members = []
        for member in self._sparkpy_room.members:
            members.append('{person}:{room}'.format(person=member.personId,
                                                    room=self._sparkpy_room.id)
                           )
        return members

    def invite(self, *args):
        for person in args:
            if sparkpy.utils.is_api_id(person, 'people'):
                self._sparkpy_room.add_member(person)
            elif '@' in person:
                self.room.add_member(email=person)
            else:
                raise ValueError('Invalid personId or email: ' + person)

    def __getattr__(self, attr):
        return getattr(self._sparkpy_room, attr)

    def __repr__(self):
        return '<ErrSparkRoom("{room}")>'.format(room=self.id)


class ErrSparkRoomOccupant(RoomOccupant, ErrSparkPerson):
    '''
    This object represents a member in a Spark Room
    '''
    def __init__(self, person, room, membership=None):
        super().__init__(person._sparkpy_person)
        self._room = room
        self.membership = membership

    @property
    def room(self):
        return self._room

    def delete(self):
        return self.membership.delete()

    def __repr__(self):
        return '<SparkRoomOccupant({person}:{room})>'.format(
            person=self.person,
            room=self.room.id)


class ErrSparkMessage(Message):
    '''
    A Cisco Spark Message for errbot.

    overrides two properties to detect if room is a group or 1:1
    '''
    @property
    def is_direct(self):
        return self.frm.room.type == 'direct'

    @property
    def is_group(self):
        return self.frm.room.type == 'group'


class ErrSparkBackend(ErrBot):
    '''
    The Spark backend for ErrBot
    '''

    def __init__(self, config):
        super().__init__(config)
        self.spark = sparkpy.Spark(config.BOT_IDENTITY)
        self.md = md()  # Needed to convert from markdown extra to markdown

    @property
    def bot_identifier(self):
        return self.spark.me

    def build_identifier(self, text_representation):
        '''
        Take a string and build an ErrBot object from it.

        This can be a single API ID for rooms and people, or two ids delimited
        by a colon.
        '''
        log.debug('Build Identifier called with {}'
                  .format(text_representation))
        if ':' in text_representation:
            person, room = text_representation.split(':')
            return ErrSparkRoomOccupant(ErrSparkPerson(person),
                                        ErrSparkRoom(room))

        decoded = sparkpy.utils.decode_api_id(text_representation)
        if decoded['path'] == 'people':
            return ErrSparkPerson(text_representation)
        elif decoded['path'] == 'rooms':
            return ErrSparkRoom(text_representation)
        else:
            raise TypeError('Invalid identifier')

    def send_message(self, message, files=None):
        log.warning('send message called with {}'.format(message.__dict__))
        super().send_message(message)
        text = self.md.convert(NEWLINE_RE.sub(r'  \n', message.body))
        self.spark.send_message(text, room_id=message.to.id)
        return

    def get_message(self, message_id):
        '''
        Take a message id, return an errbot message object
        '''
        msg = sparkpy.SparkMessage(message_id)
        message = ErrSparkMessage(msg.markdown or msg.text)
        log.debug('message personId: %s', msg.personId)
        log.debug('message roomId: %s', msg.roomId)
        message.frm = self.build_identifier('{person}:{room}'.format(
                                            person=msg.personId,
                                            room=msg.roomId))
        message.to = self.build_identifier(msg.roomId)
        return message

    def send_card(self, card):
        '''
        Implement the send_card functionality for Cisco Spark.
        Cisco Spark doesn't really support cards or html formatting
        This is subject to breakage
        '''
        # colors = {'red': 'danger',
        #           'yellow': 'warning',
        #           'green': 'success',
        #           'teal': 'info'}

        msg = '<blockquote class="{color}">'.format(color=card.color)
        msg += '<h2>{title}</h2>'.format(title=card.title)
        msg += '{link}</br>'.format(card.link)
        if card.fields:
            msg += '<ul>'
            for pair in card.fields:
                msg += '<li><b>{key}:</b> {value}</li>'.format(key=pair[0],
                                                               value=pair[1])
            msg += '</ul>'
        msg += '{body}</blockquote>card.body'.format(card.body)
        self.spark.send_message(msg, room_id=card.to.id)

    def build_reply(self, msg, text=None, private=False, threaded=False):
        reply = self.build_message(text)
        reply.frm = self.bot_identifier
        reply.to = msg.frm.room
        return reply

    def is_from_self(self, msg):
        return msg.frm.person == self.bot_identifier.id

    def rooms(self):
        return [ErrSparkRoom(room) for room in self.spark.rooms]

    def query_room(self, room):
        if sparkpy.utils.is_api_id(room, 'rooms'):
            return ErrSparkRoom(room)
        else:
            raise ValueError('Invalid roomId provided')

    def change_presence(self, status, message):
        raise NotImplementedError('Cannot change presence')

    def mode(self):
        return 'Spark'

    def event_callback(self, event):
        ''' Event will be a dict of the webhook payload '''
        pass

    def message_callback(self, event):
        message = self.get_message(event['id'])
        self.callback_message(message)
        return

    def ws_message_callback(self, ws, message):
        try:
            event = json.loads(message)
        except ValueError:
            log.error('Invalid json received from websocket: %s', event)
            return
        if event.get('url'):
            # First event received, should be our webhook url
            webhook_url = event.get('url').replace('12345', '8443')
            webhook_secret = event.get('secret')
            self.spark.create_webhook('Errbot webhook',
                                      webhook_url,
                                      'all', 'all',
                                      secret=webhook_secret)
        elif event.get('data'):
            data = event.get('data')
            log.debug('Received event: %s', data)
            resource = event['data'].get('resource', 'None')
            if resource == 'messages':
                self.message_callback(event['data']['data'])
            # elif resource == 'memberships':
            #     self.spark_memberships_callback(event['data'])
            # elif resource == 'rooms':
            #     self.spark_rooms_callback(event['data'])
            # elif resource == 'teams':
            #     self.spark_teams_callback(event['data'])
            else:
                log.debug('Unknown event type received: %s', resource)
        else:
            log.debug('Unknown event received over websocket: %s', event)
        return

    def __repr__(self):
        return '<ErrSparkBackend({id})>'.format(id=self.spark.me.id)

    def serve_forever(self):
        self.connect_callback()
        # try:
        #     while True:
        #         sleep(1)
        ws = websocket.WebSocketApp(self.bot_config.WEBSOCKET_PROXY,
                                    on_message=self.ws_message_callback)
        try:
            ws.run_forever()
        except KeyboardInterrupt:
            log.debug('KeyboardInterrupt received')
            pass
        finally:
            for hook in self.spark.webhooks.filtered(
                    lambda x: x.name == 'Errbot webhook'):
                hook.delete()
            self.disconnect_callback()
            self.shutdown()
