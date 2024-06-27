#%%
from asyncio import run, create_task, StreamReader, get_event_loop, StreamReaderProtocol, sleep
from random import randrange
import sys
import logging
from skr_mini import SKR_MINI
from agitators import Agitators, Agitator
from pico import Picos
import time

#%%
agitators = Agitators()

#%%
agitators._num_agitators=2

#%%
await agitators.connect()

# %%
await agitators.start_debugging()
# %%
await agitators.start_heating(20)
# %%
await agitators.agitators[1].start(1000)
# %%
await agitators.stop_heating()
# %%
