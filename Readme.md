
This is an errbot (http://errbot.net) backend for Cisco Spark (https://www.ciscospark.com/)

## Requirements
Python Requests


## Installation

```
git clone https://github.com/panholt/err-backend-cisco-spark.git
```

## Configuration:

```
BACKEND = 'Cisco Spark'
BOT_EXTRA_BACKEND_DIR = '/path_to/err-backend-cisco-spark'
BOT_EXTRA_PLUGIN_DIR = '/path_to/cisco-spark-webhook-plugin'
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
BOT_ADMINS = ('user@email.com',    # Email address of bot admins
          )
```

## Webserver configuration
The Cisco Spark backend will not work properly without first configuring the errbot Webserver plugin. To do so, first start errbot in the text backend and supply the proper configuration:

```
$ errbot -T
>>> /plugin config Webserver {'HOST': '0.0.0.0', 'PORT': 80,  'SSL': {'certificate': '', 'enabled': False, 'host': '0.0.0.0', 'key': '', 'port': 443}}
```

Change the HTTP and HTTPS ports to suit your environment.

Next, add the WEBHOOK_URL key to errbot's config.py to the your webhook receiver URL:

```
WEBHOOK_URL = 'http://some_host.com/incoming'
```

The Cisco Spark Backend will automatically create the Webhooks using the Cisco Spark API.

##Extra Configuration Options
Cisco Spark has a message limit of 7439 characters for the messages API. Errbot should be configured to respect this limit:
```
MESSAGE_SIZE_LIMIT = 7439
```

Cisco Spark Webhooks for bots only trigger in 1:1 rooms with the bot, or if the bot is @mentioned in a group room.
This backend will automatically register alternate prefixes for the @mention patterns so no additional prefix would be needed.
For example "@bot status" in a group room would trigger the webhook and the message payload would read "bot status", and an alternate prefix of "bot" is injected to the Errbot configuration.

##ACLs 
This backend is setup to use the personEmail field for ACL 

## Contributing

Pull requests welcome
