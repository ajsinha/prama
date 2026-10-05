# prama-sdk

The Python SDK for Prama: everything a Prama server does, from Python. It is a
client of a running server and nothing more. It never opens Prama's database and
never imports the server, so a client machine installs this package alone.

```bash
pip install prama-sdk          # httpx and PyYAML; nothing of the server
```

Requires Python 3.12 or newer, like the server it talks to.

```python
import prama_sdk as prama

client = prama.connect(username="admin", password="…")  # the server config/application.yaml names
client = prama.connect("https://prama.example.com", api_key="pk_live_…")
print(client.auth.me())
```

The guide (connecting, credentials, errors, and every namespace with worked
examples) is `docs/sdk/` in the Prama repository. Every endpoint of the server's
API has a method here; the server's build fails if one does not.

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential; see the LICENSE file in the Prama repository.
