"""
Monkey-patch: mount the pre-built React frontend as static files.
Imported by the Docker entrypoint before uvicorn loads the app.
"""
# This file is not needed at runtime — static serving is handled
# by adding StaticFiles mount in main.py when the /app/static dir exists.
