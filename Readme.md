
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
BOT_IDENTITY = {
  'id': '',                     #PersonId value from Cisco Spark
  'token' : '',                 #Bearer Token belonging to the bot
  'email' : 'bot@sparkbot.io',  #Email address for the bot account
}
```

The BOT_ADMINS key takes the personId string from Cisco Spark
```
BOT_ADMINS = ('Y2lzY29zcGFyazovL3VzL1BFT1BMRS...',    #PersonId of bot admins
          )
```

## Websocket Proxy
The WEBSOCKET_PROXY key is used to setup the Websocket.


## Contributing

Pull requests welcome
