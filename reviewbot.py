from config import digest_subject, recipients, sender, smtp, username, password, project
import simplejson
from httplib2 import Http
import smtplib
import email as emailpy
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
import datetime
from datetime import datetime as dt

SENDEMAIL = True
h = Http()


data = {"jsonrpc":"2.0","method":"allQueryNext","params":["status:open project:%s"%project,"z",25],"id":5}

resp, content = h.request( 'https://gerrit.wikimedia.org/r/gerrit/rpc/ChangeListService', 'POST',
  headers={ "Accept": "application/json,application/json,application/jsonrequest",
    "Content-Type": "application/json; charset=UTF-8"
  },
  body=simplejson.dumps(data) )


data = simplejson.loads(content)

users = {}

for user in data["result"]["accounts"]["accounts"]:
  try:
    userid = "%s"%user["id"]["id"]
    if "preferredEmail" in user:
      users[userid] = { "fullName": user["fullName"] }
      try:
        index = user["preferredEmail"].index( "wikimedia.org" )
      except ValueError:
        users[userid]["volunteer"] = False
      users[userid]["changes"] = []
  except TypeError:
    pass

change_ids = []
changes = data["result"]["changes"]
for change in data["result"]["changes"]:
  change_id = change["id"]["id"]
  change_ids.append( { "id": change_id } )

# calculate patch status
changes = {}
params = {"jsonrpc":"2.0","method":"strongestApprovals",
"params":[change_ids]}

resp, content = h.request( 'https://gerrit.wikimedia.org/r/gerrit/rpc/PatchDetailService', 'POST',
  headers={ "Accept": "application/json,application/json,application/jsonrequest",
    "Content-Type": "application/json; charset=UTF-8"
  },
  body=simplejson.dumps( params ) )

summaries = simplejson.loads(content)
for approval in summaries["result"]["summaries"]:
  if "approvals" in approval:
    status = 0
    changeId = approval["approvals"][1]["key"]["patchSetId"]["changeId"]["id"]
    for review in  approval["approvals"]:
      if "value" in review: #don't count jenkins
        if review['key']['accountId']['id'] != 75:
          status += review["value"]
    changes["%s"%changeId] = status

# organise all changes per user
for change in data["result"]["changes"]:
  change_id = "%s"%change["id"]["id"]
  key = "%s"%change["owner"]["id"]
  url = "https://gerrit.wikimedia.org/r/%s"%( change_id )
  try:
    if change_id in changes:
      status = changes[change_id]
    else:
      status = '?'

    time_string = change['lastUpdatedOn'][0:18]
    format = "%Y-%m-%d %H:%M:%S"

    try:
      d = datetime.datetime.strptime(time_string, format)
    except AttributeError:
      d = dt(*(time.strptime(time_string, format)[0:6]))

    delta = d.now() - d
    age = delta.days
    if age < 0:
      age = 0
    user = users[key]
    users[key]["changes"].append( { "subject": change["subject"], "url": url, "status": status,
     "age": age } )
  except KeyError:
    pass

# output the email
body = ""
totalchanges = 0

for u in users:
  changes = users[u]["changes"]
  def sorter(a, b):
    if a["age"] > b["age"]:
      return -1
    else:
      return 1

  changes.sort(sorter)
  if "volunteer" in users[u]:
    volunteer = "[VOLUNTEER] "
  else:
    volunteer = ""

  urlList = []
  for change in changes:
    status = change["status"]
    if status > 0:
      status = '+%s'%status
    totalchanges += 1
    urlList.append( '>>%s [%s]:\n%s\n(%s days old)\n'% (
      change["subject"], status,change["url"],
      change["age"]) )
  body += '''%s%s (%s):
###########################################

%s
'''%( volunteer, users[u]["fullName"], len(users[u]["changes"]), "\n".join( urlList ) )

if SENDEMAIL and totalchanges > 0:
  header = "%s outstanding patches awaiting review from %s\n\n"%( totalchanges, project )
  body = header + body
  s=smtplib.SMTP()
  msg = MIMEMultipart( 'alternative' )
  msg['Subject'] = digest_subject
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
  print body


