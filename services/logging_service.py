import logging
import logging.handlers

def setup_logging():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                "bot.log",
                maxBytes=1024 * 1024,
                backupCount=1
            )
        ]
    ) 