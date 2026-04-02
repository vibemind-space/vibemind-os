"""Quick start script for the Brain Nervous System server."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from web.brain_server import create_app

app = create_app(testing=False)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
