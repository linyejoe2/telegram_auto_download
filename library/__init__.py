"""
library — web video library (watch & manage downloaded videos in the browser).

media.py   ffprobe info, screenshots, sidecar metadata stored next to each video
store.py   scans the downloads folder, keeps the in-memory index, tag lists
auth.py    password hashing, signed session cookies, login rate limit
server.py  aiohttp app (API, streaming / live transcode, React frontend) and its runner
"""
