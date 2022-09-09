from threading import Event, current_thread
from flask import Flask, render_template, jsonify, request, redirect, g, stream_with_context, Response, abort

auth_server = Flask(__name__)
auth_server.config['SECRET_KEY'] = "ASDFASDFASDFADS" #Config.WebpanelSecretKey

from rpc_client import RpcClient

rpc = RpcClient("tcp://0.0.0.0:3119","Va9ItukjG06GNg9xY1ynych4l9P41X6xtTf9qlDKK4")
longPollEvents = {}

@auth_server.route('/scan',methods=['post'])
def scan():
    device = request.args.get('device')
    scanner = request.args.get('scanner')
    credential = request.args.get('credential')
    if device is None or scanner is None or credential is None:
        abort(400)
    # look up user

    for ev in longPollEvents.values():
        ev.set()

    try:
        with rpc.connect() as connection:
            connection.unlock(device,1,5,credential)
    except:
        # TODO Log this
        pass
    return "OK"

@auth_server.route("/ping")
def ping():
    return Response("pong")

@auth_server.route("/rpc")
def rpctest():
    #with rpc.connect() as connection:
    #    return Response(str(connection.list_devices()))
    with rpc.connect() as connection:
        connection.unlock("ftdi://ftdi:232:AM01QCWE/1",1,5,"doesntmatter")
    return "OK"

@auth_server.route("/poll")
def longpoll():
    if current_thread() not in longPollEvents:
        longPollEvents[current_thread()] = Event()

    lpe = longPollEvents[current_thread()]
    if lpe.wait(5.0):
        lpe.clear()
        return Response("Scanned!")
    else:
        return Response("Nothing")

@auth_server.route("/doordisplay")
def door_display():
    return render_template('container.html')





