from asyncio import run, create_task, StreamReader, get_event_loop, StreamReaderProtocol, sleep
from random import randrange
import sys
import logging
from skr_mini import SKR_MINI
from pico import Picos

logging.basicConfig(filename='log.log', encoding='utf-8', level=logging.DEBUG)

# To calibrate the SKR's position set the x, y & z position of the "sensor_1_pickup_position" on line 10 of the file skr_mini.py


async def main():
    # To stop the script running hit enter
    create_task(cancel_on_enter_keypress())

    # Connects to the motion control board
    await skr.connect()

    # Move the head to the X & Y location of a sensor (plate, column, row)
    # await skr.move_to(1, 0, 0, True)

    # Move to, grab and raise a sensor from the rack
    # await skr.collect_sensor(1, 0, 0)

    # Return a sensor to the rack
    # await skr.dropoff_sensor(1, 1, 0)

    # Open the head's jaws
    # await skr.open_jaw()

    # move sensors about randomly
    # Make sure to set the starting "positions" below (Line 43)
    # await move_sensors_randomly()

    # print(await picos.check_connections())

    await skr.disconnect()
    # await picos.close()

# init 2x3x12 array to represent the positions a sensor can be in the well plate
positions = [[[False]*12 for _i in range(3)], [[False]*12 for _i in range(3)]]

positions[1][0][0] = True


def pick_random_position():
    plate = randrange(1) + 1
    col = randrange(2)
    # row = randrange(12)
    row = randrange(6)

    return plate, col, row


def pick_random_sensor():
    position: tuple[int, int, int]
    while True:
        position = pick_random_position()
        plate, col, row = position
        if positions[plate][col][row]:
            break
    return position


def pick_random_destination():
    position: tuple[int, int, int]
    while True:
        position = pick_random_position()
        plate, col, row = position
        if not positions[plate][col][row]:
            break
    return position


async def cancel_on_enter_keypress():
    global close
    reader = StreamReader()
    pipe = sys.stdin
    loop = get_event_loop()
    await loop.connect_read_pipe(lambda: StreamReaderProtocol(reader), pipe)

    async for _line in reader:
        # print(f'Got: {line.decode()!r}')
        close = True
        await skr.disconnect()


async def move_sensors_randomly():
    while not close:
        plate1, col1, row1 = pick_random_sensor()
        plate2, col2, row2 = pick_random_destination()
        print(
            f"moving {plate1}, {col1}, {row1*2} to {plate2}, {col2}, {row2*2}")
        # await skr.move_sensor(plate1, col1, row1, plate2, col2, row2)
        await skr.collect_sensor(plate1, col1, row1)
        # values = await picos.check_connections()
        # if abs(values[0]) < 10000:
        #     break
        # print(values)

        await skr.dropoff_sensor(plate2, col2, row2)
        positions[plate1][col1][row1] = False
        positions[plate2][col2][row2] = True

        # await skr.home_jaw()

close = False
skr = SKR_MINI()
picos = Picos()
run(main())
