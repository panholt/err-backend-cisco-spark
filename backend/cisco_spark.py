# -*- coding: utf-8 -*-
import json
import logging
import time
import requests
import sys
import re

from collections import OrderedDict
from time import sleep

from errbot.errBot import ErrBot
from errbot.backends.base import Message, Person, Room, RoomOccupant
from errbot.rendering import md

# Can't use __name__ because of Yapsy
log = logging.getLogger('errbot.backends.spark')

# Constants
API_BASE = 'https://api.ciscospark.com/v1/'
PERSON_PREFIX = 'Y2lzY29zcGFyazovL3VzL1BFT1BMRS'
ROOM_PREFIX = 'Y2lzY29zcGFyazovL3VzL1JPT00'
PERSON_CACHE ={}
NEWLINE_RE = re.compile(r'(?<!\n)\n(?!\n)') # Single \n only, not \n\n
BOT = None
SESSION = requests.session()

def get_membership_by_room(roomId):
    resp = SESSION.get(API_BASE + 'memberships',
                       params={'roomId': roomId,
                               'personId': BOT.bot_identifier.personId})
    if resp.status_code == 200:
        try:
            return resp.json()['items'][0]['id']
        except:
            log.debug('Error occured getting membership. Details: {}'
                      .format(resp.text))
    else:
        process_api_error(resp)
    return

def retry_after_hook(resp, *args, **kwargs):
    '''
    Requests request hook. Looks for a 429 response
    Will sleep for the proper interval and then retry
    '''
    if resp.status_code == 429:
        sleepy_time = int(resp.headers.get('Retry-After', 15))
        log.debug('Received 429 Response. Sleeping for: {} secs'
                  .format(sleepy_time))
        sleep(sleepy_time)
        return SESSION.send(resp.request)
    else:
        return

def process_api_error(resp):
    log.debug('Received a: {} response from Cisco Spark'
              .format(resp.status_code))
    log.debug('Error details: {}'.format(resp.text))
    raise Exception('Received a: {} response from Cisco Spark'
                    .format(resp.status_code))


def get_all_pages(resp):
    '''
    Takes a response object and returns a list of all items across all pages
    '''
    data = resp.json()['items']
    while resp.links.get('next'):
        resp = SESSION.get(resp.links['next']['url'])
        if resp.status_code != 200:
            process_api_error(resp)
        data += resp.json().get('items', [])
    return data

class SparkPerson(Person):
    '''
    This class represents a Spark User
    '''

    def __init__(self,
                 personId=None,
                 personEmail=None,
                 personDisplayName=None,
                 isModerator=None,
                 isMonitor=None,
                 created=None):

        if not any((personId, personEmail)):
            raise Exception('SparkPerson needs either an id or email address')

        if personId is not None and not personId.startswith(PERSON_PREFIX):
            raise Exception('Invalid Spark Person ID: {}'.format(personId))
        elif personEmail is not None and '@' not in personEmail:
            raise Exception('Invalid Spark Person Email address {}'
                            .format(personEmail))

        self._personId = personId
        self._personEmail = personEmail
        self._personDisplayName = personDisplayName
        self._isModerator = isModerator
        self._isMonitor = isMonitor

    @property
    def personId(self):
        if self._personId is None:
            self.get_person_details()
        return self._personId

    @personId.setter
    def personId(self, value):
        if not value.startswith(PERSON_PREFIX):
            raise ValueError('Valid Spark Person ID required')
        self._personId = value
        return

    @property
    def personEmail(self):
        if self._personEmail is None:
            self.get_person_details()
        return self._personEmail

    @personEmail.setter
    def personEmail(self, value):
        if '@' not in value:
            raise ValueError('Valid Email Address is required')
        else:
            self._personEmail = value

    @property
    def personDisplayName(self):
        if self._personDisplayName is None:
            self.get_person_details()
        return self._personDisplayName

    @personDisplayName.setter
    def personDisplayName(self, value):
        self._personDisplayName = value
        return

    @property
    def person(self):
        return self.personId

    @property
    def nick(self):
        return self.personEmail

    @property
    def isMonitor(self):
        return self._isMonitor

    @property
    def isModerator(self):
        return self._isModerator

    @property
    def fullname(self):
        return self._personDisplayName

    @property
    def client(self):
        return ''

    aclattr = personEmail

    def get_person_details(self):
        if self._personId:  # Use the protected attrib to avoid recursion
            data = PERSON_CACHE.get(self._personId)
            if data:
                self.personId = data['id']
                self.personDisplayName = data['displayName']
                self.personEmail = data['emails'][0]
                return
            else:
                resp = SESSION.get('{}people/{}'.format(API_BASE, 
                                                        self.personId))
        elif self._personEmail:
            resp = SESSION.get(API_BASE + 'people',
                               params={'email': self.personEmail})
        elif self._personDisplayName:
            resp = SESSION.get(API_BASE + 'people',
                               params={'displayName': self.personDisplayName})
        if resp.status_code == 200:
            data = resp.json()
            if data.get('items'):
                data = data.get('items')[0]
            PERSON_CACHE[data['id']] = data
            self.personId = data['id']
            self.personDisplayName = data['displayName']
            self.personEmail = data['emails'][0]
        else:
            process_api_error(resp)
        return

    def __eq__(self, other):
        return str(self) == str(other)

    def __unicode__(self):
        return self.personId

    __str__ = __unicode__


class SparkRoomOccupant(SparkPerson, RoomOccupant):
    def __init__(self,
                 room,
                 personId=None,
                 membershipId=None,
                 personEmail=None,
                 personDisplayName=None,
                 isModerator=None,
                 isMonitor=None,
                 created=None):

        super().__init__(personId,
                         personEmail,
                         personDisplayName,
                         isModerator,
                         isMonitor,
                         created)

        self._membershipId = membershipId
        self._room = room

    @property
    def room(self):
        return self._room

    @property
    def membershipId(self):
        return self._membershipId
    

class SparkRoom(Room):
    '''
    This class represents a Spark room
    '''
    def __init__(self,
                 roomId,
                 title,
                 roomType,
                 isLocked,
                 lastActivity,
                 created,
                 teamId=None):

        self._roomId = roomId
        self._title = title
        self._roomType = roomType
        self._isLocked = isLocked
        self._lastActivity = lastActivity
        self._created = created
        self._teamId = teamId
        super().__init__()

    @property
    def roomId(self):
        return self._roomId

    @roomId.setter
    def roomId(self, value):
        if value.startswith(ROOM_PREFIX):
            self._roomId = value
        else:
            raise ValueError('Invalid Room ID Provided')

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        if self.roomType == 'direct':
            raise ValueError('Cannot change the title of a direct room')
        else:
            resp = SESSION.put(API_BASE + 'rooms/{}'.format(self.roomId),
                               json={'title': value})
            if resp.status_code == 200:
                self._title = value
                return
            elif resp.status_code == 409:
                # Policy response. Room is moderated
                raise AttributeError('Cannot change the title of locked room')
            else:
                process_api_error(resp)
                return

    @property
    def isLocked(self):
        return self._isLocked

    @property
    def lastActivity(self):
        return self._lastActivity

    @property
    def roomType(self):
        return self._roomType

    @property
    def created(self):
        return self._created

    @property
    def teamId(self):
        return self._teamId

    @property
    def topic(self):
        return self._title

    @topic.setter
    def topic(self, value):
        self.title = value
        return

    @property
    def occupants(self):
        _occupants = []
        resp = SESSION.get('https://api.ciscospark.com/v1/memberships',
                           params={'roomId': self.roomId})
        if resp.status_code != 200:
            process_api_error(resp)

        data = get_all_pages(resp)

        for membership in data:
            _occupants.append(SparkRoomOccupant(
                              room=self,
                              membershipId=membership['id'],
                              personId=membership['personId'],
                              personEmail=membership['personEmail'],
                              isModerator=membership['isModerator'],
                              isMonitor=membership['isMonitor'],
                              created=membership['created'],
                              personDisplayName=membership['personDisplayName']
                              ))
        return _occupants

    def invite(self, person):
        if self.roomType == 'direct':
            raise Exception('Cannot add a person to a 1:1 room')
        data = {'roomId': self.roomId}
        if person.startswith(PERSON_PREFIX):
            data['personId'] = person
        elif '@' in person:
            data['personEmail'] = person
        else:
            raise Exception('Invalid Identifier: "{}" ' +
                            'Must be an email address or Spark personId'
                            .format(person))

        resp = SESSION.post(API_BASE + 'memberships',
                            json=data)
        if resp.status_code == 409:
            log.debug('Received 409 Response adding user to room. Body: {}'
                      .format(resp.text))
            raise Exception('Unable to add user to room. ' +
                            'Either room is locked or user is already in room')
        elif resp.status_code == 200:
            return
        else: 
            process_api_error(resp)

    def create(self):
        pass 

    def leave(self):
        log.debug('Leaving room: {} with membership: {}'
                  .format(self.roomId, get_membership_by_room(self.roomId)))

        resp = SESSION.delete(API_BASE + 'memberships/{}'
                              .format(get_membership_by_room(self.roomId)))
        if resp.status_code == 409:
            raise Exception('Unable to leave moderated room')
        elif resp.status_code != 204:
            process_api_error(resp)
        return

    def destroy(self):
        resp = SESSION.delete(API_BASE + 'rooms/{}'.format(self.roomId))
        if resp.status_code == 409:
            raise Exception('Unable to delete moderated room')
        elif resp.status_code != 204:  # Member deleted
            process_api_error(resp)
        return

    def kick(self, person):
        if isinstance(person, SparkRoomOccupant):
            resp = SESSION.delete(API_BASE + 'memberships/{}'.format(person.membershipId))
            if resp.status_code == 204:
                return
            else:
                process_api_error(resp)
        else:
            return


    def join(self):
        raise NotImplemented('Cannot join rooms. Must be added instead')

    def __eq__(self, other):
        return self.roomId == other

    def __hash__(self):
        return hash(self.roomId)

    def __unicode__(self):
        return self.roomId

    __str__ = __unicode__


class SparkRoomList(OrderedDict):
    '''
    subclassed dict to fetch missing rooms
    '''

    def __missing__(self, key):
        if key.startswith(ROOM_PREFIX):
            resp = SESSION.get(API_BASE + 'rooms/{}'.format(key))
            if resp.status_code != 200:
                process_api_error(resp)

            data = resp.json()
            self[key] = SparkRoom(roomId=data['id'],
                                  title=data['title'],
                                  roomType=data['type'],
                                  isLocked=data['isLocked'],
                                  lastActivity=data['lastActivity'],
                                  created=data['created'],
                                  teamId=data.get('teamId')  # May not exist
                                  )
            return self[key]

class SparkMessage(Message):
    @property
    def is_direct(self):
        return self.to.roomType == 'direct'

    @property
    def is_group(self):
        log.debug('message.is_group accessed. Message is: {}'.format(message.to.roomType))
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
        self._webhook_url = config.WEBHOOK_URL
        self.md = md()
        self._rooms = SparkRoomList()
        self.build_alt_prefixes()
        # self._rooms = SparkRoomList([(room.roomId, room)
        #                             for room in self.rooms()])

        if not any((hook['targetUrl'] == self.webhook_url
                   for hook in self.get_webhooks())):
            log.debug('No Webhook found matching targetUrl: {}'
                      .format(self.webhook_url))
            self.create_webhook(self.webhook_url)
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

    def create_webhook(self, url, secret=False):
        # TODO implement secret checking at plugin
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
        resp = SESSION.get(API_BASE + 'rooms', params={'teamId': teamId})
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

        message = Message(text)
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
                                       title=room['title'],
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

    def create_one_on_one_room(self, person, message):
        '''
        Sends a 1:1 Message to a user and returns a SparkRoom Object
        '''
        data = {'markdown': message}
        if person.startswith(PERSON_PREFIX):
            data['toPersonId'] = person
        elif '@' in person:
            data['toPersonEmail'] = person
        else:
            raise ValueError('Invalid Person Identifier: {}'.format(person))
        
        log.debug('Preparing to send message with body: {}'.format(data))
        resp = SESSION.post(API_BASE + 'messages', json=data)
        if resp.status_code == 200:
            _data = resp.json()
            log.debug('Response payload is: {}'.format(_data))
            return self._rooms[_data['roomId']]
        else:
            log.debug('Received error response: {} {}'.format(resp.status_code, resp.text))
            raise Exception('Error sending message to {}. Error: {}'.format(person, resp.status_code))
            return


    def serve_forever(self):
        log.debug('Entering serve forever')
        try:
            self.connect_callback()
            while True:
                sleep(300)

        except KeyboardInterrupt:
            log.debug('KeyboardInterrupt received')
            pass
        except Exception as e:
            log.debug('Caught Exception: {}'.format(e))
        finally:
            log.info('Received keyboard interrupt. Shutdown requested.')
            self.disconnect_callback()
            self.shutdown()
