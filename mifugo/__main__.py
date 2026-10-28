"""python -m mifugo  ->  the web app on http://127.0.0.1:8000"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "mifugo.web:app",
        host=os.environ.get("MIFUGO_HOST", "127.0.0.1"),
        port=int(os.environ.get("MIFUGO_PORT", "8000")),
    )
