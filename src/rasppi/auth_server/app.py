import logging
logger = logging.getLogger(__name__)
from auth_server import auth_server

if __name__ == '__main__':
    logger.info("Application starting up")
    auth_server.run( host="0.0.0.0",port=8443)