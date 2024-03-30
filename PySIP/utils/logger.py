import logging
from logging.handlers import RotatingFileHandler
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener

def setup_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    logger.addHandler(ch)

    # file handler
    fh = RotatingFileHandler('PySIP.log')
    fh = RotatingFileHandler('PySIP.log', maxBytes=1000000, backupCount=5)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    # formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)

    return logger

logger = setup_logger()
console_handler = logger.handlers[0]
file_handler = logger.handlers[1]

def get_call_logger(call_id):
    call_logger = logging.LoggerAdapter(logger, {'call_id': call_id})
    return call_logger

