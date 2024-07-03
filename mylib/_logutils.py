import os
import logging

#
#
#
logging.basicConfig(
    format='[ %(asctime)s %(levelname)s %(filename)s ] %(message)s',
    datefmt='%c',
    level=os.environ.get('PYTHONLOGLEVEL', 'WARNING').upper(),
)
logging.captureWarnings(True)
Logger = logging.getLogger(__name__)
