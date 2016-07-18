
This is an errbot (http://errbot.net) backend for Cisco Spark (https://www.ciscospark.com/) 

## Requirements
Python Requests


## Installation

```
git checkout https://github.com/panholt/err-backend-cisco-spark.git
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
BOT_IDENTITY = {
  'id': '',                     #PersonId value from Cisco Spark
  'token' : '',                 #Bearer Token belonging to the bot
  'email' : 'bot@sparkbot.io',  #Email address for the bot account
}
```

The BOT_ADMINS key takes the personId string from Cisco Spark
BOT_ADMINS = ('Y2lzY29zcGFyazovL3VzL1BFT1BMRS8yZTM3YjNkMi0zZTI0LTRlNTgtYWVkYi1kMjgzZWM1NGY2Mjc',    #PersonId of bot admins
             )

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

## Contributing

1. Fork it!
2. Create your working branch: `git checkout -b some-new-feature`
3. Commit your changes: `git commit -am 'Add some new feature'`
4. Push to the branch: `git push origin some-new-feature`
5. Submit a pull request 