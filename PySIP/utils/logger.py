import logging
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
import queue

def get_call_logger(call_id):
    call_logger = logging.LoggerAdapter(logger, {'call_id': call_id})
    return call_logger

def setup_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    logger.addHandler(ch)

    # file handler
    fh = RotatingFileHandler('PySIP.log', maxBytes=1000000, backupCount=5)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    # formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)

    return logger

def setup_async_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # file handler
    fh = RotatingFileHandler('PySIP.log')
    fh.setLevel(logging.DEBUG)

    # formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)

    log_q = queue.SimpleQueue()
    queue_handler = QueueHandler(log_q)
    listener = QueueListener(log_q, ch, fh)

    logger.addHandler(queue_handler)

    return logger, ch, fh, listener

# If we want to use unblocking logger we have to un-comment this
# logger, console_handler, file_handler, listener = setup_async_logger()

logger = setup_logger()
console_handler = logger.handlers[0]
file_handler = logger.handlers[1]


