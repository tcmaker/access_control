import json
from operator import itemgetter
from typing import List
from configuration import Config, Configuration, ConfigurationException
from itertools import groupby
import logging
import subprocess
from time import sleep
logger = logging.getLogger("webpanel")
from datadog_logger import get_datadog_logger
dd_logger = get_datadog_logger("authorization_service", "authorization_service")
from flask import Flask, render_template, jsonify, request, redirect, g, stream_with_context, Response
from flask_httpauth import HTTPDigestAuth
from sqlalchemy.orm import Session
from datetime import datetime
from pytz import utc

from models import Activity#, AccessRequirement, Credential
from multiprocessing import Queue
from queue import Empty

webpanel = Flask(__name__)
webpanel.config['SECRET_KEY'] = Config.WebpanelSecretKey

from aws_wrapper import TestAws

auth = HTTPDigestAuth()

@webpanel.template_filter()
def hashid(int):
    return Config.HashId.encode(int)

@webpanel.template_filter()
def is_fatal(s : str):
    return "text-light bg-dark" if s.startswith("FATAL") or s.startswith("CRITIAL") else ""

@webpanel.template_filter()
def is_error(s : str):
    return "text-danger" if s.startswith("ERROR") else ""

@webpanel.template_filter()
def is_warning(s : str):
    return "text-warning" if s.startswith("WARNING") else ""

@webpanel.template_filter()
def is_info(s : str):
    return "text-info" if s.startswith("INFO") else ""

@webpanel.template_filter()
def is_debug(s : str):
    return "text-secondary" if s.startswith("DEBUG") else ""

@webpanel.template_filter()
def pretty_past(d : datetime):
    now = datetime.now()
    diff = now - d
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(second_diff // 60) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(second_diff // 3600) + " hours ago"
    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(day_diff // 7) + " weeks ago"
    if day_diff < 365:
        return str(day_diff // 30) + " months ago"
    return str(day_diff // 365) + " years ago"


@webpanel.teardown_appcontext
def shutdown_session(exception=None):
    if hasattr(g,'dbsession'):
        g.dbsession.close()


@auth.get_password
def get_pw(username):
    if username in Config.WebpanelLogin:
        return Config.WebpanelLogin.get(username)

@webpanel.route('/')
@auth.login_required
def hello_world():
    return render_template('index.html',beavis='stuff',ctx="root")

@webpanel.route('/hardware')
@auth.login_required
def hardware():
    g.dbsession = Config.ScopedSession()
    #boards = g.dbsession.query(Board).all()
    #facilities = g.dbsession.query(Facility).order_by(Facility.name).all()
    return render_template('configuration.html', ctx="hardware")

@webpanel.route('/facilities')
@auth.login_required
def facilities():
    return render_template('facilities.html',ctx="facilities")



@webpanel.route('/config')
@auth.login_required
def configuration():
    with open('door_config.yaml', 'r') as configfile:
        config_text = configfile.read()
    return render_template('configuration.html',body=config_text,filepath=Config.FileName,ctx="configuration")


@webpanel.route('/query_hardware', methods=['post'])
@auth.login_required
def query_hardware():
    #rapidly clicking query could cause problems.
    q: Queue = webpanel.config['squeue']
    w: Queue = webpanel.config['wqueue']
    q.put(("query",))
    try:
        status = w.get(True, 10.0)
    except Empty:
        status = []

    g.dbsession = Config.ScopedSession()

    return "<br />".join(status)
    #return render_template('queried_devices.html', devices=devices)

@webpanel.route('/testaws', methods=['post'])
@auth.login_required()
def testAws():
    cc = Configuration(request.form['config'])
    try:
        TestAws(cc.RawConfig['aws'])
        return "Success"
    except Exception as e:
        return str(e)

@webpanel.route("/validate-config",methods=['post'])
@auth.login_required
def validateConfig():
    try:
        cc = Configuration(request.form['config'])
        return "OK"
    except ConfigurationException as ce:
        return str(ce)

@webpanel.route("/update-config",methods=['post'])
@auth.login_required
def update_config():
    try:
        newconfig = request.form['config']
        cc = Configuration(newconfig)
        with open(Config.FileName,'w') as out:
            out.write(newconfig)
        Config.Reload()
        q: Queue = webpanel.config['squeue']
        w: Queue = webpanel.config['wqueue']
        q.put(("reload",))
        try:
            w.get(True, 3.00) #wait for a response before doing anything else
        except Empty: #TODO
            pass
        return redirect("/config")
    except ConfigurationException as ce:
        return jsonify({'result':'failed', "message" : str(ce) })


from math import ceil

@webpanel.route('/activity')
@auth.login_required
def activity():
    page = request.args['page'] if 'page' in request.args else 1
    try:
        page = int(page)
    except:
        page = 1

    page = max(1,page)
    perPage = 200
    g.dbsession = Config.ScopedSession()

    total = g.dbsession.query(Activity).count()
    pages = ceil(total / perPage)
    page = min(pages, page)

    pagerange = range(max(0,page-3)+1,min(pages, page+2)+1)

    activity = g.dbsession.query(Activity).order_by(Activity.timestamp.desc()).offset((page - 1) * perPage).limit(perPage)

    return render_template('activity.html',activity=activity,ctx="activity",page=page, pages=pages,pagerange=pagerange)

@webpanel.route('/users')
@auth.login_required
def users():
    return "Disabled for now"
    page = request.args['page'] if 'page' in request.args else 1
    try:
        page = int(page)
    except:
        page = 1

    page = max(1, page)
    perPage = 200

    g.dbsession = Config.ScopedSession()
    now = datetime.now(utc)

    total = g.dbsession.query(Credential).filter(Credential.expiration > now).count()
    pages = ceil(total / perPage)
    page = min(pages, page)

    pagerange = range(max(0, page - 3) + 1, min(pages, page + 2) + 1)


    members = g.dbsession.query(Credential).filter(Credential.expiration > now)\
        .order_by(Credential.memberid)\
        .order_by(Credential.priority)\
        .order_by(Credential.expiration).offset((page - 1) * perPage).limit(perPage).all()

    membersgrouped = dict((k,list(v)) for k,v in groupby(members, lambda m : m.memberid))

    for k,v in membersgrouped.items():
        #blah = list(v)
        print(k,len(list(v)))

    return render_template('users.html', activity=activity, members=membersgrouped,ctx="users",page=page, pages=pages,pagerange=pagerange)


@webpanel.route('/export')
@auth.login_required
def export():
    g.dbsession = Config.ScopedSession()
    activity = g.dbsession.query(Activity).order_by(Activity.timestamp.desc())

    def generate():
        yield f"Time,Facility,MemberId,Authcode,Result\r\n"
        a: Activity
        for a in activity:
            yield f"{a.timestamp.strftime('%c')},{a.facility},{a.memberid},{a.credentialref},{a.result}\r\n"

    return Response(stream_with_context(generate()),mimetype="text/csv")


@webpanel.template_filter()
#def format_active(ar : AccessRequirement):
def format_active(ar):
    return "ZING"
    if ar.always_active():
        return "Always"
    else:
        if ar.is_active():
            return "Now"
        else:
            return f"On {ar.next_active()}"


@webpanel.route('/diagnostics')
@auth.login_required
def diagnostics():
    q: Queue = webpanel.config['squeue']
    w: Queue = webpanel.config['wqueue']
    q.put(("status",))
    try:
        status = w.get(True,0.250)
    except Empty:
        status = {}
    g.dbsession = Config.ScopedSession()
    facility_map = {}
    for f in status:
        facility_map[f] = ( Config.Facilities[f].board, Config.Facilities[f].relay )
    #requirements : List[AccessRequirement] = list(g.dbsession.query(AccessRequirement).order_by(AccessRequirement.requiredpriority.desc()).all())
    #TODO
    requirements = []
    requiredLevel = 0
    for r in requirements:
        if r.is_active():
            requiredLevel = max(requiredLevel,r.requiredpriority)

    return render_template('diagnostics.html',facility_status=status,facility_map=facility_map,requirements=requirements,rlevel=requiredLevel,ctx="diagnostics")

@webpanel.route('/lock',methods=['post'])
@auth.login_required
def lock():
    try:
        board = request.form['board']
        relay = int(request.form['index'])
        q: Queue = webpanel.config['squeue']
        q.put(("lock",board,relay,None))
        sleep(0.5) #less than ideal
        return redirect("/diagnostics")
    except:
        return redirect("/diagnostics")



@webpanel.route('/unlock',methods=['post'])
@auth.login_required
def unlock():
    try:
        board = request.form['board']
        relay = int(request.form['index'])
        duration = int(float(request.form['duration']))
        dd_logger.info(f"Manual unlock of door for {duration} seconds triggered.")
        q: Queue = webpanel.config['squeue']
        q.put(("unlock",board,relay,duration,None))
        sleep(0.5)  # less than ideal
        return redirect("/diagnostics")
    except:
        return redirect("/diagnostics")

@webpanel.route('/testfob')
@auth.login_required
def test_fob():
    if 'fobnumber' not in request.args:
        return redirect("/diagnostics")
    fob_to_test = str(int(request.args['fobnumber']))
    q: Queue = webpanel.config['squeue']
    w: Queue = webpanel.config['wqueue']
    try:
        while True:
            w.get(block=False)
    except Empty:
        pass

    q.put(("checkfob", fob_to_test))
    result = w.get(True, 1.0)

    try:
        return render_template("fobtest.html",results=result, tested_fob=request.args['fobnumber'])
    except:
        logger.error(f"Failed to render. Result={result}")
        return "Oops"


@webpanel.route('/log')
@auth.login_required
def log():
    with subprocess.Popen(['tail','-n','200',Config.LogFile],stdout=subprocess.PIPE) as proc:
        rl = proc.stdout.readlines()

    def doencode(l):
        return l.decode('utf-8').replace('\n',"")

    grouped = []
    item = []
    ll: str
    for ll  in map(doencode,rl):
        if not ll[:5] in ["INFO:", "DEBUG","ERROR","CRITI","FATAL","WARNI"]:
            item.append(ll)
        else:
            if len(item) > 0:
                grouped.append(item)
            item = [ll]
    if len(item) > 0:
        grouped.append(item)

    grouped.reverse()

    def collapse_group(l):
        if len(l) == 1:
            return [l[0]]
        else:
            return [l[0],"\n".join(l[1:])]

    return render_template('log.html',logsize=len(rl),logcontents=map(collapse_group,grouped),ctx="log")

