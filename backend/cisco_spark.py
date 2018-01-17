import logging
import re

from time import sleep
from errbot.core import ErrBot
from errbot.backends.base import Message, Person, Room, RoomOccupant
from errbot.rendering import md
import sparkpy

log = logging.getLogger('errbot.backends.spark')


# This incantation summons a single \n only.
# Not multiple \n's
# Not a \n preceeded by two spaces and a non whitespace character
# (which would indicate "proper" markdown usage)
#
# Typically used as NEWLINE_RE.replace('  \n', somestring)
# In order to fixup "soft breaks" into linebreaks that markdown understands
NEWLINE_RE = re.compile(r'(?<!\n)(?<!\w\s{2})\n(?!\n)')


class ErrSparkPerson(Person):
    '''
    This class represents a Person in Cisco Spark. This is a wrapper over
    sparkpy.models.people.SparkPerson
    '''

    def __init__(self, person, session=False):
        if isinstance(person, sparkpy.SparkPerson):
            self._sparkpy_person = person
            if not session:
                session = person.parent
        elif sparkpy.utils.is_api_id(person, 'people'):
            self._sparkpy_person = sparkpy.SparkPerson(person, parent=session)
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

    args: a string of the roomId or a sparpy.models.room.SparkRoom
    '''
    def __init__(self, room, session):
        if isinstance(room, sparkpy.SparkRoom):
            self._sparkpy_room = room
        if sparkpy.utils.is_api_id(room, 'rooms'):
            self._sparkpy_room = sparkpy.SparkRoom(room, parent=session)
        else:
            raise TypeError('Invalid Cisco Spark Room id: ' + room)

    def join(self):
        raise NotImplemented('Cannot join rooms. Must be added instead')

    def leave(self):
        self._sparkpy_room.remove_member(self.spark.me.id)

    def destroy(self):
        self._sparkpy_room.remove_all_members()
        self._sparkpy_room.delete()

    def exists(self):
        return True

    def joined(self):
        return True

    @classmethod
    def create(cls, title, members=[], moderators=[], message=None):
        pass

    @property
    def topic(self):
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
                                                    room=self._sparkpy_room.id))
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
    def __init__(self, *args, **kwargs):
        self.sparkpy_msg = kwargs.pop('sparkpy_msg')
        super().__init__(*args, **kwargs)

    def __getattr__(self, attr):
        return getattr(self.sparkpy_msg, attr)

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
        self.build_alt_prefixes()

    @property
    def bot_identifier(self):
        return self.spark.me

    def build_alt_prefixes(self):
        words = self.bot_identifier.displayName.split(' ')
        new_prefixes = []
        if len(words) > 1:
            for x in range(len(words)):
                new_prefixes.append(' '.join(words[:x + 1]))
        else:
            new_prefixes.append(self.bot_identifier.displayName)

        try:
            bot_prefixes = self.bot_config.BOT_ALT_PREFIXES.split(',')
        except AttributeError:
            bot_prefixes = list(self.bot_config.BOT_ALT_PREFIXES)

        self.bot_alt_prefixes = tuple(new_prefixes + bot_prefixes)
        # Errbot wont consider alt prefixes if the key doesn't exist in the config
        if len(self.bot_config.BOT_ALT_PREFIXES) < 1:
            self.bot_config.BOT_ALT_PREFIXES = self.bot_alt_prefixes
        return

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
            return ErrSparkRoomOccupant(ErrSparkPerson(person, self.spark),
                                        ErrSparkRoom(room, self.spark))

        decoded = sparkpy.utils.decode_api_id(text_representation)
        if decoded['path'] == 'people':
            return ErrSparkPerson(text_representation, self.spark)
        elif decoded['path'] == 'rooms':
            return ErrSparkRoom(text_representation, self.spark)
        else:
            raise TypeError('Invalid identifier')

    def send_message(self, message, files=None):
        super().send_message(message)
        text = self.md.convert(NEWLINE_RE.sub(r'  \n', message.body))
        self.spark.send_message(text, room_id=message.to.id)
        return

    def get_message(self, message_id, parent):
        '''
        Take a message id, return an errbot message object
        '''
        msg = sparkpy.SparkMessage(message_id, parent=parent)
        message = ErrSparkMessage(msg.markdown or msg.text, sparkpy_msg=msg)
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
        msg += '{link}</br>'.format(link=card.link)
        if card.fields:
            msg += '<ul>'
            for pair in card.fields:
                msg += '<li><b>{key}:</b> {value}</li>'.format(key=pair[0],
                                                               value=pair[1])
            msg += '</ul>'
        msg += '{body}</blockquote>'.format(body=card.body)
        self.spark.send_message(msg, room_id=card.to.room.id)

    def build_reply(self, msg, text=None, private=False, threaded=False):
        reply = self.build_message(text)
        reply.frm = self.bot_identifier
        reply.to = msg.frm.room
        return reply

    def is_from_self(self, msg):
        return msg.frm.person == self.bot_identifier.id

    def rooms(self):
        return [ErrSparkRoom(room, self.spark) for room in self.spark.rooms]

    def query_room(self, room):
        if sparkpy.utils.is_api_id(room, 'rooms'):
            return ErrSparkRoom(room, self.spark)
        else:
            raise ValueError('Invalid roomId provided')

    def change_presence(self, status, message):
        raise NotImplementedError('Cannot change presence')

    @property
    def mode(self):
        return 'Spark'

    # Event callbacks for specific webhooks types
    def spark_message_callback(self, event, session):
        if event['event'] == 'deleted':
            log.debug('Message deleted. Not processing further.')
            return
        elif event['actorId'] == self.bot_identifier.id:
            log.debug('Ignoring message from self')
            return
        else:
            message = self.get_message(event['data']['id'],
                                       parent=sparkpy.SparkRoom(event['data']['roomId'],
                                                                parent=self.spark))
            self.callback_message(message)
        return

    def spark_rooms_callback(self, event):
        return

    def spark_teams_callback(self, event):
        return

    def spark_memberships_callback(self, event):
        return

    def spark_webhook_callback(self, event):
        ''' Event will be a dict of the webhook payload '''
        resource = event.get('resource', 'None')
        if resource == 'messages':
            self.spark_message_callback(event, self.spark)
        elif resource == 'memberships':
            self.spark_memberships_callback(event)
        elif resource == 'rooms':
            self.spark_rooms_callback(event)
        elif resource == 'teams':
            self.spark_teams_callback(event)
        else:
            log.debug('Unknown event type received: %s', resource)

    def serve_forever(self):
        self.connect_callback()
        try:
            while True:
                sleep(1)
        except KeyboardInterrupt:
            log.debug('KeyboardInterrupt received')
            pass
        finally:
            self.disconnect_callback()
            self.shutdown()

    def __repr__(self):
        return '<ErrSparkBackend({id})>'.format(id=self.spark.me.id)

