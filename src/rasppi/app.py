from configuration import Config
import logging

logging.getLogger('sqlalchemy.engine').setLevel(logging.FATAL)
logging.getLogger('sqlalchemy.pool').setLevel(logging.FATAL)
logging.getLogger('sqlalchemy.orm').setLevel(logging.FATAL)
logging.getLogger('werkzeug').setLevel(logging.FATAL)

logger = logging.getLogger("app")
from webpanel import webpanel

import multiprocessing as mp
from multiprocessing import  shared_memory

from authorization_service import AuthorizationService


if __name__ == '__main__':
    Debug = False
    if not Debug:
        sq = mp.Queue()
        wq = mp.Queue()
        p = mp.Process(target=AuthorizationService, args=(sq,wq))
        p.start()
    else:
        from queue import Queue
        sq = Queue()
        wq = Queue()
    webpanel.config['squeue'] = sq
    webpanel.config['wqueue'] = wq
    logger.info("Application starting up")
    webpanel.run( host="0.0.0.0",port=8443, debug=Debug)