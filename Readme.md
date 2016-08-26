
This is an errbot (http://errbot.net) backend for Cisco Spark (https://www.ciscospark.com/)

## Requirements
Python Requests (https://github.com/kennethreitz/requests)

Python Websocket-client (https://github.com/liris/websocket-client)


## Installation

```
git clone https://github.com/panholt/err-backend-cisco-spark.git
```

## Configuration:

```
BACKEND = 'Cisco Spark'
BOT_EXTRA_BACKEND_DIR = '/path_to/err-backend-cisco-spark'
```

to your config.py

## Authentication

The BOT_IDENTITY needs to be updated to contain the personId, Bearer Token, and email address of the bot
Create bot accounts at https://developer.ciscospark.com/add-bot.html

```
BOT_IDENTITY = {'token' : ''} # Bearer Token belonging to the bot
```

The BOT_ADMINS key takes the personId string from Cisco Spark
```
BOT_ADMINS = ('userid@email.com',    # Email Address of bot admins
          )
```

## Websocket Proxy
The WEBSOCKET_PROXY key is used to setup the Websocket.

##Extra Configuration Options
Cisco Spark has a message limit of 7439 characters for the messages API. Errbot should be configured to respect this limit:
```
MESSAGE_SIZE_LIMIT = 7439
```

Cisco Spark Webhooks for bots only trigger in 1:1 rooms with the bot, or if the bot is @mentioned in a group room.
This backend will automatically register alternate prefixes for the @mention patterns so no additional prefix would be needed.
For example "@bot status" in a group room would trigger the webhook and the message payload would read "bot status", and an alternate prefix of "bot" is injected to the Errbot configuration.

## Contributing

Pull requests welcome
