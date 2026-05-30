import os
import sys

from python_socks.sync import Proxy

host = os.environ["DST"]
port = int(os.environ["DPORT"])
purl = os.environ["PROXY"]
try:
    p = Proxy.from_url(purl)
    s = p.connect(dest_host=host, dest_port=port, timeout=15)
    s.close()
    print("OK")
    sys.exit(0)
except Exception as e:
    print("FAIL", type(e).__name__, str(e)[:80])
    sys.exit(1)
