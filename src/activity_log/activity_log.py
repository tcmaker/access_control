__VERSION__ = "1.0"
import logging
import pathlib
import sys, os
from math import ceil
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import Table, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import paho.mqtt.client as mqtt
from json import loads,dumps
from yaml import load
from yaml.loader import SafeLoader

logging.getLogger('sqlalchemy.engine').setLevel(logging.FATAL)
logging.getLogger('sqlalchemy.pool').setLevel(logging.FATAL)
logging.getLogger('sqlalchemy.orm').setLevel(logging.FATAL)
logging.getLogger('werkzeug').setLevel(logging.FATAL)

from flask import Flask, render_template, jsonify, request, redirect, g, stream_with_context, Response, abort

ActivityBase = declarative_base()

class Activity(ActivityBase):
    __tablename__  = 'activity'

    id = Column(Integer, primary_key=True)
    facility = Column(String, nullable=False)
    memberid = Column(String)
    credentialref = Column(String) #convenience
    timestamp = Column(DateTime, nullable=False)
    result = Column(String, nullable=False)

    def toJSON(self):
        return {
            "facility" : self.facility,
            "person" : self.memberid,
            "code" : self.credentialref,
            "timestamp" : self.timestamp.isoformat(),
            'result' : self.result
        }

activity_log = Flask(__name__)

@activity_log.teardown_appcontext
def shutdown_session(exception=None):
    if hasattr(g,'dbsession'):
        g.dbsession.close()

@activity_log.route('/activity')
#@auth.login_required
def activity():
    page = request.args['page'] if 'page' in request.args else 1
    try:
        page = int(page)
    except:
        page = 1

    page = max(1,page)
    perPage = 200
    g.dbsession = activity_log.config['DBSESSION']()

    total = g.dbsession.query(Activity).count()
    pages = ceil(total / perPage)
    page = min(pages, page)

    pagerange = range(max(0,page-3)+1,min(pages, page+2)+1)

    activity = g.dbsession.query(Activity).order_by(Activity.timestamp.desc()).offset((page - 1) * perPage).limit(perPage)

    return jsonify([a.toJSON() for a in activity])

class LogListener:
    def __init__(self, broker, logfile, topic):
        self._topic = topic
        engine = create_engine(f"sqlite:///{logfile}")
        Session = sessionmaker(bind=engine)
        # session = Session()
        self.ScopedSession = scoped_session(Session)
        ActivityBase.metadata.create_all(engine.engine)

        self._client = mqtt.Client("activity_log")
        self._client.on_connect = self.on_connect
        self._client.connect(broker, 1883)

        self._client.on_message = self.on_mqtt_message

    def start(self):
        self._client.loop_start()

    def stop(self):
        self._client.loop_stop()

    def on_connect(self, client, userdata, flags, rc):
        self._client.subscribe(self._topic)

    def on_mqtt_message(self, client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
        try:
            topic = message.topic
            payload = loads(str(message.payload.decode('utf-8')))
            if topic == self._topic and payload['type'] == "access":
                db = self.ScopedSession()
                try:

                    entry = Activity(facility=payload['hostname'],
                                     memberid=payload['username'],
                                     credentialref=payload['uid'],
                                     timestamp=datetime.fromtimestamp(payload['time']),
                                     result=payload['access'])
                    db.add(entry)
                    db.commit()
                finally:
                    db.close()
        except:
            pass

def run_log_listener(broker, activity_db, mqtt_topic, secret_key=os.urandom(16)):
    ll = LogListener(broker,activity_db,mqtt_topic)
    ll.start()
    activity_log.config['SECRET_KEY'] = secret_key  # Config.WebpanelSecretKey
    activity_log.config['DBSESSION'] = ll.ScopedSession
    activity_log.run()
    ll.stop()

def process_args(sysargs):
    import argparse

    parser = argparse.ArgumentParser(
        description="""Access control hardware server""", epilog="I'll put my name in here at some point")

    parser.add_argument('-c', '--config', action='store', dest='config', default=None,
                        help="specify non-default configuration file")
    parser.add_argument('-v', '--version', action='store_true', dest='version', help="show version and exit")
    parser.add_argument('-q', '--quiet', action='store_true', dest='quiet', help="suppress non-error messages")
    parser.add_argument('-g', '--debug', action='store_true', dest='debug', help="show all log messages")

    args = parser.parse_args(sysargs)
    return args

if __name__ == '__main__':
    args = process_args(sys.argv[1:])

    if args.version:
        print(f"{sys.argv[0]} {__VERSION__}")
        exit(0)

    logging.basicConfig(level=logging.ERROR if args.quiet else logging.DEBUG if args.debug else logging.INFO)

    # load the configuration
    configfile = pathlib.Path('./config.yaml')
    if args.config is not None:
        configfile = pathlib.Path(args.config)

    with open(str(configfile.absolute())) as stream:
        config = load(stream, Loader=SafeLoader)

    run_log_listener(**config['log_listener'])