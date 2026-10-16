import urllib.request
import re
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request("https://sig.misiones.gob.ar/mapas/monitor/rio-parana/", headers={"User-Agent": "Mozilla/5.0"})
content = urllib.request.urlopen(req, context=ctx).read().decode("utf-8", errors="ignore")

for line in content.splitlines():
    if "const DATOS" in line or "DATOS =" in line:
        print(line.strip())
