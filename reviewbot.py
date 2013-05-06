from config import digest_subject, recipients, sender, smtp, username, password, project, \
  BUGZILLA_PRODUCT, BUGZILLA_COMPONENTS, SENDEMAIL, GERRIT_URL, BUGZILLA_REPORT_DAYS
import simplejson
from httplib2 import Http
import feedparser
import smtplib
import email as emailpy
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
import datetime
from datetime import datetime as dt
from datetime import timedelta
import time

def calculate_age( timestamp ):
  time_string = timestamp[0:18]
  format = "%Y-%m-%d %H:%M:%S"

  try:
    d = datetime.datetime.strptime( time_string, format )
  except AttributeError:
    d = dt( *( time.strptime( time_string, format )[0:6] ) )

  delta = d.now() - d
  age = delta.days
  if age < 0:
    age = 0
  return age

#run...

print dt.today()

h = Http()
DIVIDER = '''
###########################################

'''
if GERRIT_URL:
  url = GERRIT_URL
else:
  url = False

body = ""
totalchanges = 0
newbugs = 0
closedbugs = 0

if url:
  resp, content = h.request( url, 'GET',
    headers={ "Accept": "application/json,application/json,application/jsonrequest",
      "Content-Type": "application/json; charset=UTF-8"
    } )


  # deal with weird gerrit response...
  content = content.split( '\n' )
  content = content[1:] # wtf?
  data = simplejson.loads( '\n'.join( content ) )

  patches = {}
  for change in data:
    user = change["owner"]["name"]
    subj = change["subject"]
    url = 'https://gerrit.wikimedia.org/r/%s'%change["_number"]

    #go through reviews..
    reviews = change["labels"]["Code-Review"]
    likes = 0
    dislikes = 0
    status = 0
    reviewers = []

    if "recommended" in reviews:
      likes += 1
      reviewers.append( reviews["recommended"]["name"] )

    if "disliked" in reviews:
      dislikes += 1
      reviewers.append( reviews[ "disliked" ][ "name" ] )

    if "rejected" in reviews:
      dislikes += 2
      reviewers.append( reviews[ "rejected" ][ "name" ] )

    #calculate status
    if dislikes > 0:
      status = -dislikes
    else:
      status = likes

    patch = { "user": user, "subject": subj, "status": status,
      "url": url,
      "age": calculate_age( change["created"] ), "reviewers" : reviewers }
    if user in patches:
      patches[user][ "changes" ].append( patch )
    else:
      patches[ user ] = { "changes": [ patch ] }

  # calculate patch status

  # output the email

  for patch_username in patches:
    changes = patches[ patch_username ][ "changes" ]
    def sorter(a, b):
      if a[ "age" ] > b[ "age" ]:
        return -1
      else:
        return 1

    changes.sort(sorter)

    summary = []
    for change in changes:
      status = change["status"]
      if status > 0:
        status = '+%s'%status
      totalchanges += 1
      if len( change[ "reviewers" ] ) == 0:
        reviewees = "n/a"
      else:
        reviewees = "(Reviewed by " + ",".join( change[ "reviewers" ] ) + ")"
      summary.append( '>>%s [%s] %s:\n%s\n(%s days old)\n'% (
        change["subject"], status, reviewees, change["url"],
        change["age"]) )
    body += '''%s (%s):
  %s
  %s
  '''%( patch_username, len( patches[ patch_username ][ "changes" ] ), DIVIDER, "\n".join( summary ) )

if BUGZILLA_REPORT_DAYS:
  yd = dt.now() - timedelta( days=BUGZILLA_REPORT_DAYS )
  yesterday = yd.isoformat(' ')[0:10]
  bug_url = 'https://bugzilla.wikimedia.org/buglist.cgi?chfieldfrom=' + yesterday
  for c in BUGZILLA_COMPONENTS:
    bug_url += '&component=%s'%( c )
  bug_url += '&chfieldto=Now&product=' + BUGZILLA_PRODUCT + '&query_format=advanced&title=Bug%20List&ctype=atom'

  open_bug_url = bug_url + '&chfield=%5BBug%20creation%5D&resolution=---'
  closed_bug_url = bug_url + '&chfield=resolution&resolution=FIXED'

  # open bugs
  feed = feedparser.parse( open_bug_url )
  body += '***\n\nNew bugs:%s'%( DIVIDER )
  for entry in feed["entries"]:
    newbugs +=1
    body += '%s\n%s\n\n'%( entry['title_detail']['value'], entry["link"] )

  if newbugs == 0:
    body += 'No bugs opened since yesterday\n\n'

  # closed bugs
  feed = feedparser.parse( closed_bug_url )
  body += '***\n\nClosed bugs:%s'%( DIVIDER )
  for entry in feed["entries"]:
    closedbugs +=1
    body += '%s\n%s\n\n'%( entry['title_detail']['value'], entry["link"] )

  if closedbugs == 0:
    body += 'No bugs closed since yesterday\n\n'

#write email
if GERRIT_URL and BUGZILLA_REPORT_DAYS:
  header = "%s outstanding patches awaiting review, %s bugs closed and %s new bugs from %s\n\n"%( totalchanges, closedbugs, newbugs, project )
elif GERRIT_URL:
  header = "%s outstanding patches awaiting review from %s\n\n"%( totalchanges, project )
else:
  header = "%s bugs closed and %s new bugs from %s\n\n"%( closedbugs, newbugs, project )

body = header + body
body += DIVIDER + 'Fork me on github: https://github.com/jdlrobson/gerrit-review-mailbot'
try:
  subject = digest_subject.format( totalchanges, newbugs, closedbugs )
except AttributeError:
  subject = digest_subject.replace( '{0}', '%s'%totalchanges )
  subject = subject.replace( '{1}', '%s'%newbugs )
  subject = subject.replace( '{2}', '%s'%closedbugs )

if SENDEMAIL and ( totalchanges > 0 or newbugs > 0 or closedbugs > 0 ):
  s=smtplib.SMTP()
  msg = MIMEMultipart( 'alternative' )
  msg['Subject'] = subject
  msg['From'] = sender
  msg['To'] = recipients

  part1 = MIMEText(body, 'plain')
  msg.attach(part1)

  mailBody = msg.as_string()
  s.connect( smtp )
  s.login(username, password)
  s.sendmail(msg["From"],msg["To"],mailBody)
  print "message sent"
else:
  print "posting to terminal"
  print "Subject: " + subject
  print body


