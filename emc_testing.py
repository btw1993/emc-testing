from asyncio import run
from agitators import Agitators
from pico import Picos
import logging
from skr_mini import SKR_MINI

logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', filename='log.log',
                    encoding='utf-8', level=logging.DEBUG,  datefmt='%Y-%m-%d %H:%M:%S')


async def main():
    await connect_all()
    await enter_emmisions_testing_mode()
    while True:
        print(await picos.check_connections())
    await disconnect_all()


async def connect_all():
    await skr.connect()
    await agitators.connect()
    await picos.connect()


async def disconnect_all():
    await skr.disconnect()
    await agitators.close()
    await picos.close()


async def enter_emmisions_testing_mode():
    await agitators.start()
    await agitators.start_heating_cooling_cycle()
    await skr.run_home_move_loop()
    await picos.start_read()


async def exit_emmisions_testing_mode():
    await agitators.stop()
    # await skr.cancel_sd_file()
    await picos.start_read()


close = False
skr = SKR_MINI()
picos = Picos()
agitators = Agitators()
run(main())
