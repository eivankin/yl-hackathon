import json
import time
import os
from stable import make_turn

TESTS_DIR = 'tests'

for filename in os.listdir(TESTS_DIR):
    with open(os.path.join(TESTS_DIR, filename)) as inp:
        data = json.load(inp)

    target = None
    start_time = time.time()
    make_turn(data)
    print(f'Time elapsed: {(time.time() - start_time) * 1000:.3f} ms')
