import sys
for mod in list(sys.modules.keys()):
    if 'agentqe.vision' in mod:
        del sys.modules[mod]

from agentqe.vision.config import get_vision_config
config = get_vision_config()
print('python:', config.omniparser_python)

import subprocess
result = subprocess.run([config.omniparser_python, '-c', 'import torch; import ultralytics; import transformers; print("OK")'], capture_output=True, text=True, timeout=10, shell=False)
print('returncode:', result.returncode)
print('stdout:', result.stdout)
print('stderr:', result.stderr[:200] if result.stderr else 'none')