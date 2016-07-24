# -*- coding: utf-8 -*-
import json
import logging
import time
import requests
import sys

from time import sleep
from collections import OrderedDict
from errbot import webhook
from errbot.errBot import ErrBot
from errbot.backends.base import Message, Person, Room, RoomOccupant

# Can't use __name__ because of Yapsy
log = logging.getLogger('errbot.backends.spark')

# Constants
API_BASE = 'https://api.ciscospark.com/v1/'
HEADERS = {'Content-type': 'application/json; charset=utf-8'}
PERSON_PREFIX = 'Y2lzY29zcGFyazovL3VzL1BFT1BMRS'
ROOM_PREFIX = 'Y2lzY29zcGFyazovL3VzL1JPT00'


def get_membership_by_room(roomId):
    resp = requests.get(API_BASE + 'memberships',
                        headers=HEADERS, params={'roomId': roomId})
    if resp.status_code == 200:
        try:
            return resp.json()['id']
        except:
            log.debug('Error occured getting membership. Details: {}'
                      .format(resp.text))
    else:
        process_api_error(resp)
    return


def process_api_error(resp):
    log.debug('Recevied a: {} response from Cisco Spark'
              .format(resp.status_code))
    log.debug('Error details: {}'.format(resp.text))
    raise Exception('Recevied a: {} response from Cisco Spark'
                    .format(resp.status_code))


def get_all_pages(resp):
    '''
    Takes a response object and returns a list of all items across all pages
    '''
    data = resp.json()['items']
    while resp.links.get('next'):
        resp = requests.get(resp.links['next']['url'], headers=HEADERS)
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

    aclattr = person

    def get_person_details(self):
        resp = requests.get(API_BASE + 'people/{}'.format(self.personId),
                            headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            self.personId = data['id']
            self.personDisplayName = data['displayName']
            self.personEmail = data['emails'].pop()
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

        self._room = room

    @property
    def room(self):
        return self._room


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
            resp = requests.put(API_BASE + 'rooms/{}'.format(self.roomId),
                                headers=HEADERS, json={'title': value})
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
        resp = requests.get('https://api.ciscospark.com/v1/memberships',
                            params={'roomId': self.roomId}, headers=HEADERS)
        if resp.status_code != 200:
            process_api_error(resp)

        data = get_all_pages(resp)

        for membership in data:
            _occupants.append(SparkRoomOccupant(
                              room=self,
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

        resp = requests.post(API_BASE + 'memberships',
                             json=data, headers=HEADERS)
        if resp.status_code == 409:
            log.debug('Received 409 Response adding user to room. Body: {}'
                      .format(resp.text))
            raise Exception('Unable to add user to room. ' +
                            'Either room is locked or user is already in room')
        return

    def create(self):
        resp = requests.post(API_BASE + 'rooms', headers=HEADERS,
                             json={'title': self.title})
        data = resp.json()
        self.roomId = data['id']
        return

    def leave(self):
        log.debug('Leaving room: {} with membership: {}'
                  .format(self.roomId, get_membership_by_room(self.roomId)))

        resp = requests.delete(API_BASE + 'memberships/{}'
                               .format(get_membership_by_room(self.roomId)),
                               headers=HEADERS)

        if resp.status_code == 409:
            raise Exception('Unable to leave moderated room')
        elif resp.status_code != 204:  # Member deleted
            process_api_error(resp)
        return

    def destroy(self):
        resp = requests.delete(API_BASE + 'rooms/{}'.format(self.roomId),
                               headers=HEADERS)
        if resp.status_code == 409:
            raise Exception('Unable to delete moderated room')
        elif resp.status_code != 204:  # Member deleted
            process_api_error(resp)
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
            resp = requests.get(API_BASE + 'rooms/'.format(key),
                                headers=HEADERS)
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


class SparkBackend(ErrBot):
    '''
    The Spark backend for ErrBot
    '''

    def __init__(self, config):
        super().__init__(config)
        identity = config.BOT_IDENTITY
        self.token = identity.get('token', None)
        if not self.token:
            log.fatal('Cannot find API token.')
            sys.exit(1)
        else:
            HEADERS['Authorization'] = 'Bearer {}'.format(self.token)
        self.bot_identifier = self.build_identifier(identity.get('id'))
        self._display_name = identity['email'].split('@')[0]
        self._email = identity['email']
        self._webhook_url = config.WEBHOOK_URL
        self._rooms = SparkRoomList([(room.roomId, room)
                                    for room in self.rooms()])

        if not any((hook['targetUrl'] == self.webhook_url
                   for hook in self.get_webhooks())):
            log.debug('No Webhook found matching targetUrl: {}'
                      .format(self.webhook_url))
            self.create_webhook()

    @property
    def display_name(self):
        return self._display_name

    @property
    def email(self):
        return self._email

    @property
    def webhook_url(self):
        return self._webhook_url

    @property
    def mode(self):
        return 'spark'

    def get_webhooks(self):
        log.debug('Fetching Webhooks')
        resp = requests.get(API_BASE + 'webhooks', headers=HEADERS)
        if resp.status_code != 200:
            process_api_error(resp)
        data = resp.json()
        return data['items']

    def create_webhook(self):
        return requests.post(API_BASE + 'webhooks', headers=HEADERS,
                             json={'name': 'Spark Errbot Webhook',
                                   'targetUrl': self.webhook_url,
                                   'resource': 'all',
                                   'event': 'all'})

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
            return self._rooms[roomId]
        # The core plugin for create room expects a room object back
        else:
            room = SparkRoom(roomId=None,
                             title=roomId,
                             roomType='group',
                             isLocked=False,
                             lastActivity=None,
                             created=None,
                             teamId=None
                             )
            return room

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
        data = {'markdown': message.body}
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
        resp = requests.post(API_BASE + 'messages', headers=HEADERS, json=data)
        if resp.status_code == 200:
            return
        else:
            raise Exception('Recevied a {} from {} with body {}'
                            .format(resp.status_code,
                                    resp.request.url,
                                    resp.request.body))

    def change_presence(self, status, message):
        log.debug('Presence is not implemented by the Spark backend')
        return

    def decrypt_message(self, message_id):
        """
        Decrypt a message received from a webhook event

        :returns:
            An instance of :class:`~Message`.
        """

        resp = requests.get(API_BASE + 'messages/{}'
                            .format(message_id), headers=HEADERS)
        if resp.status_code != 200:
            process_api_error(resp)

        data = resp.json()
        text = data.get('text', '')

        log.debug('Text before substitution: {}'.format(text))
        log.debug('Display name is: {}'.format(self.display_name))
        if text.startswith(self.display_name):
            text = text.replace(self.display_name + ' ', '', 1)
        log.debug('Text after substituion: {}'.format(text))

        message = Message(text)
        message.frm = self.build_identifier(data.get('personId'),
                                            room_id=data.get('roomId'))
        room = self.query_room(data.get('roomId'))

        if room.roomType == 'group':
            message.to = self.build_identifier(room.roomId)
        elif room.roomType == 'direct':
            message.to = self.build_identifier(self.bot_identifier.personId,
                                               room_id=room.roomId)
        return message

    def rooms(self):
        """
        Return a list of rooms the bot is currently in.

        :returns:
            A list of :class:`~SparkRoom` instances.
        """

        resp = requests.get(API_BASE + 'rooms', headers=HEADERS)
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
