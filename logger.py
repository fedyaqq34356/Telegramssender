import logging
from pathlib import Path
from datetime import datetime


def setup_logger():
    Path("logs").mkdir(exist_ok=True)
    
    log_file = f"logs/{datetime.now().strftime('%Y-%m-%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)


logger = setup_logger()